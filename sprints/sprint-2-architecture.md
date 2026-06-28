# Sprint 2 Architecture — Manifest, Messaging-Rich Edition

Stack stays as-is: **Flask (Python) + SQLite + vanilla JS**. No rewrite. Sprint 2 adds
a messaging layer on top of the working Sprint 1 app rather than replacing it.

---

## 1. What carries over vs. what's new

| Already built (Sprint 1) | New in Sprint 2 |
|---|---|
| Strategy (GoF) — `llm_strategy.py` | State (GoF) — `state_machine.py` |
| Builder (GoF) — `pdf_builder.py` | Observer (GoF) — `event_bus.py` |
| Pipes-and-Filters (EIP) — `pipeline.py` | Publish-Subscribe (EIP) — `event_bus.py` + `sockets.py` |
| SQLite drafts table — `database.py` | Message Router (EIP) — `router.py` |
| | Audit trail — `audit_log` table + `audit.py` |

That's already 3 EIPs (Pipes-and-Filters carries over, Pub-Sub + Message Router are
new) and 4 GoF patterns total (2 carried over, 2 new) — comfortably clears the "at
least 3 EIPs / at least 2 GoF" bar.

**Key talking point for your presentation:** Observer (GoF, object-design level) and
Publish-Subscribe (EIP, integration level) are the *same idea at two abstraction
levels* — `event_bus.py` is the Observer pattern, and it's also what implements the
Pub-Sub EIP. That's not two unrelated boxes to check, it's one piece of code that
satisfies both requirements honestly.

---

## 2. High-level architecture

```
                         ┌─────────────────────────────┐
                         │   Frontend (static/index.html) │
                         │   - REST calls (fetch)          │
                         │   - Socket.IO client (CDN)       │
                         └───────────┬─────────────────┘
                                     │ HTTP POST /api/drafts/<id>/generate
                                     │ WS join_draft / state_changed / step_complete
                                     ▼
┌────────────────────────────────────────────────────────────────────┐
│                          Flask app (app.py)                        │
│                                                                      │
│   router.py  ──▶  pipeline.py (filters)  ──▶  state_machine.py     │
│  (Message Router)   (Pipes-and-Filters)         (GoF State)        │
│        │                    │                        │             │
│        │                    ▼                        ▼             │
│        │            llm_strategy.py            event_bus.py        │
│        │            (GoF Strategy)            (GoF Observer /      │
│        │            pdf_builder.py             Pub-Sub broker)     │
│        │            (GoF Builder)                    │             │
│        │                                     ┌────────┴────────┐    │
│        │                                     ▼                 ▼    │
│        │                              sockets.py          audit.py  │
│        │                          (WS subscriber)    (DB subscriber)│
│        ▼                                     │                 │    │
│  database.py  ◀──────────────────────────────┴─────────────────┘    │
│  (drafts + audit_log tables, SQLite)                                │
└────────────────────────────────────────────────────────────────────┘
```

`event_bus.py` is the hub: nothing downstream of the pipeline talks to the WebSocket
or the database directly. Filters just publish events; `sockets.py` and `audit.py`
are independent subscribers. That decoupling is the actual point of Pub-Sub — not
just "we used WebSockets somewhere."

---

## 3. GoF pattern #3 — State (`state_machine.py`)

Classic GoF shape: a `DraftContext` holds the current `DraftState`; each state decides
what the next state is. Not a transition table — this is deliberately polymorphic so
it's unambiguously "the State pattern" if your professor asks.

```python
class DraftState(ABC):
    name: str
    def on_enter(self, ctx: "DraftContext"): ...
    @abstractmethod
    def next(self, event: str, ctx: "DraftContext") -> "DraftState": ...

class GeneratingResumeState(DraftState):
    name = "GENERATING_RESUME"
    def on_enter(self, ctx):
        ctx.bus.publish("draft.state_changed", draft_id=ctx.draft_id, to_state=self.name)
    def next(self, event, ctx):
        if event == "RESUME_GENERATED":
            return HumanizingResumeState()
        if event == "ERROR":
            return FailedState(previous=self)
        return self

class DraftContext:
    def __init__(self, draft_id, bus):
        self.draft_id = draft_id
        self.bus = bus
        self.retry_count = 0
        self.state: DraftState = IdleState()

    def handle(self, event: str):
        from_state = self.state.name
        self.state = self.state.next(event, self)
        if self.state.name != from_state:
            self.bus.publish("draft.state_changed", draft_id=self.draft_id,
                              from_state=from_state, to_state=self.state.name)
            self.state.on_enter(self)
```

### States
`IDLE → VALIDATING → GENERATING_RESUME → HUMANIZING_RESUME → SCORING_ATS →
GENERATING_COVER_LETTER → GENERATING_COMPANY_FIT → AGGREGATING → READY_FOR_REVIEW →
COMPLETED`, with `FAILED` reachable from any generating/scoring/aggregating state.

### Events
`SUBMIT, VALIDATION_OK, VALIDATION_FAILED, RESUME_GENERATED, HUMANIZE_DONE,
ATS_SCORED, COVER_LETTER_GENERATED, COMPANY_FIT_GENERATED, AGGREGATE_DONE,
USER_APPROVES, REGENERATE, ERROR, RETRY`

### Guards
- `IDLE → VALIDATING` only if `job_description` and `candidate_profile` are non-empty (existing `validate_inputs` filter logic, now also a state guard)
- Each `GENERATING_*` state checks `ctx.regen_target` before running — `None`/`"full"` runs everything; `"cover_letter"` skips straight past resume/ATS steps. **This guard is what Message Router implements** (section 5).
- `FAILED → RETRY` only if `ctx.retry_count < 3`; otherwise falls back to `IDLE` with an error shown to the user.

---

## 4. GoF pattern #4 — Observer / Pub-Sub broker (`event_bus.py`)

```python
class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable):
        self._subscribers.setdefault(event_name, []).append(handler)

    def publish(self, event_name: str, **payload):
        for handler in self._subscribers.get(event_name, []):
            handler(**payload)
```

Deliberately the simplest possible Subject in the GoF sense — no external broker,
no extra infra, no new failure modes for a single-process Render deploy. `sockets.py`
and `audit.py` each call `bus.subscribe(...)` once at startup and never touch each
other.

**Stretch/optional, not required:** swap this for Flask-SocketIO's Redis message
queue backend if you want to namedrop a real broker in the presentation. Not worth
the infra risk in a 4-week sprint — mention it as "how this would scale," don't build it.

---

## 5. EIP — Message Router (`router.py`)

```python
def route_request(payload: dict) -> list[Filter]:
    target = payload.get("regen_target", "full")
    full_chain = [generate_resume, humanize_resume, score_ats,
                  generate_cover_letter, generate_company_fit]
    if target == "full":
        return full_chain
    if target == "resume":
        return full_chain[:3]          # resume + humanize + ATS only
    if target == "cover_letter":
        return [full_chain[3]]
    if target == "company_fit":
        return [full_chain[4]]
    raise ValueError(f"Unknown regen_target: {target}")
```

This is a content-based router on `regen_target`, and it's the backbone of a real
product feature: **"regenerate just the cover letter" buttons** on the results page,
instead of re-running the whole pipeline (and burning a fresh LLM call on a resume
that was already fine). Good architecture and a UX improvement at the same time.

---

## 6. EIP — Publish-Subscribe transport (`sockets.py`)

```python
from flask_socketio import SocketIO, join_room

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on("join_draft")
def handle_join(data):
    join_room(f"draft_{data['draft_id']}")

def register_socket_subscribers(bus):
    bus.subscribe("draft.state_changed", lambda **kw: socketio.emit(
        "state_changed", kw, room=f"draft_{kw['draft_id']}"))
    bus.subscribe("draft.step_complete", lambda **kw: socketio.emit(
        "step_complete", kw, room=f"draft_{kw['draft_id']}"))
```

**No background job queue needed.** The pipeline still runs synchronously inside the
`/generate` request (same as Sprint 1) — but because the WebSocket connection is
independent of the HTTP request, `socketio.emit()` calls made *during* that request
arrive at the browser in real time, while the request is still "in flight." The
frontend never polls; it just listens. When the HTTP response finally comes back
with the full result, the UI already shows it was generated step by step.

### WebSocket event list
| Event | Payload | When |
|---|---|---|
| `state_changed` | `{draft_id, from_state, to_state}` | every state machine transition |
| `step_complete` | `{draft_id, step}` | each filter finishes |
| `generation_complete` | `{draft_id}` | `READY_FOR_REVIEW` reached |
| `generation_error` | `{draft_id, step, message}` | `FAILED` reached |

Frontend: one `<script src="https://cdn.socket.io/4.7.5/socket.io.min.js">` tag, no
React/npm needed — keeps `static/index.html` as a single vanilla-JS file.

---

## 7. Audit trail (`audit.py`)

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id    INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    from_state  TEXT,
    to_state    TEXT,
    payload     TEXT,              -- JSON snapshot
    created_at  TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
)
```

`audit.py` subscribes to the same bus and writes one row per event — it never talks
to `sockets.py` or `state_machine.py` directly, which is the whole point of routing
everything through Pub-Sub.

```python
def register_audit_subscriber(bus):
    bus.subscribe("draft.state_changed", lambda **kw: record_event(
        kw["draft_id"], "state_changed", kw.get("from_state"), kw["to_state"]))
    bus.subscribe("draft.step_complete", lambda **kw: record_event(
        kw["draft_id"], kw["step"]))
```

**Reconstructable:** `GET /api/drafts/<id>/audit` replays every row ordered by
`created_at` into a timeline — "Generated resume at 10:02:01am → humanized at
10:02:31am → ATS scored 78% at 10:02:33am → cover letter generated at 10:02:48am."
The `drafts` table stays the fast-read source of truth for current content; the
audit log is the append-only mutation history you replay to answer "how did we get
here."

---

## 8. New/changed API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/drafts/<id>/generate` | Body `{regen_target}`. Replaces the old "generate everything" call. Routes → pipeline → state machine → bus. |
| GET | `/api/drafts/<id>/audit` | Reconstructed timeline for that draft |
| GET | `/api/drafts/<id>/state` | Current state machine state (for resume-after-refresh) |
| WS | `join_draft` `{draft_id}` | Subscribes the socket to that draft's room |
| *(unchanged)* | `/api/upload-resume`, `/api/templates`, `/resume.pdf`, `/cover-letter.pdf` | Sprint 1 routes, untouched |

---

## 9. Folder structure

```
JobPack/
├── app.py                 # Flask app + routes + SocketIO init
├── router.py               # NEW — Message Router (EIP)
├── event_bus.py             # NEW — Observer (GoF) / Pub-Sub broker (EIP)
├── state_machine.py         # NEW — State (GoF)
├── sockets.py                # NEW — WebSocket gateway
├── audit.py                   # NEW — audit_log writer + reconstruct_draft()
├── llm_strategy.py          # Strategy (GoF) — unchanged
├── pdf_builder.py            # Builder (GoF) — unchanged
├── pipeline.py                # Pipes-and-Filters (EIP) — filters now also bus.publish()
├── database.py                 # + audit_log table
├── infographic.py
├── requirements.txt            # + flask-socketio, eventlet
├── Procfile                     # web: gunicorn -k eventlet -w 1 app:app
└── static/index.html             # + socket.io-client CDN script, progress UI
```

---

## 10. Deployment

- Same single Render web service — no new infra.
- `Procfile` changes to `web: gunicorn -k eventlet -w 1 app:app` — Flask-SocketIO
  needs an async worker (eventlet/gevent) and a single worker process unless you add
  a Redis-backed message queue for multi-worker fan-out. One worker is fine for a
  class project's traffic.
- Add `flask-socketio` and `eventlet` to `requirements.txt`.

---

## 11. Four-week incremental plan

**Week 1 — Plumbing first (highest-risk piece, do it early):**
`event_bus.py` + `sockets.py`, minimal frontend socket listener that just logs raw
events to the console. Goal: prove a message published on the backend shows up in
the browser in real time, end to end, before building anything on top of it.

**Week 2 — State machine:**
`state_machine.py`, wire `DraftContext` into the existing `/generate` route in place
of the direct `pipeline.run()` call. `pipeline.py` filters call `bus.publish(...)` at
each step. Replace the frontend spinner with a live step-by-step progress list.

**Week 3 — Message Router + audit trail:**
`router.py` + `regen_target` on the generate endpoint, plus "regenerate just this"
buttons per artifact on the results page. `audit.py` + `audit_log` table + a
"History" tab in the UI rendering the reconstructed timeline.

**Week 4 — Guards, retry, polish:**
`FAILED` state + `retry_count` guard + error UI. Update `README.md` with all 4 EIPs
/ GoF patterns and where they live. Deploy with the `eventlet` worker. End-to-end
test: full generate, single-artifact regenerate, a forced failure + retry, and audit
reconstruction. Record the demo.

---

## 12. README outline (for submission)

1. What Manifest does (carry over from Sprint 1 README)
2. Sprint 2 additions: messaging-rich architecture overview (the diagram in §2)
3. EIPs table: Pipes-and-Filters / Publish-Subscribe / Message Router — one
   paragraph each, file + line pointers
4. GoF table: Strategy / Builder / State / Observer — one paragraph each, same
5. State machine diagram (states/events/guards from §3)
6. WebSocket event list (table from §6)
7. Audit trail: schema + how to reconstruct a draft's history
8. Updated deploy instructions (`eventlet` worker note)
