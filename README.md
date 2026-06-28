# Manifest — AI Job Application Generator

> *Transforming potential into opportunity.*

Paste a job description + your profile → get a tailored résumé PDF, cover letter PDF, and company-fit infographic — powered by AI, with real-time generation progress over WebSockets.

**Live demo:** https://manifest-studio.onrender.com

---

## What it does

- **Tailored Résumé** — ATS-optimized, humanized, keyword-matched to the job description
- **Cover Letter** — Three-paragraph, professional, addressed to the company
- **Company Fit Report** — Pros/cons + fit score + career coach advice
- **ATS Score** — Keyword match % with matched/missing keywords shown
- **10 Resume Templates** — Classic, Modern Tech, Multicolumn, Minimalist, Executive Banner, Bold Header, Split Column, Simple Sidebar, Professional, Compact Pro
- **Draft Management** — Save, reopen, edit inline, and compare ≥2 drafts
- **File Upload** — Upload PDF, DOCX, or TXT résumé instead of pasting
- **Live Progress** — watch each generation step update in real time over WebSockets, no polling
- **Per-Artifact Regeneration** — regenerate just the cover letter or just the company-fit report without re-running everything
- **Audit Trail** — every generation step is logged and replayable, including point-in-time reconstruction of past content

---

## Setup (local)

### 1. Clone and open in PyCharm
```bash
git clone https://github.com/daniellep03/Job-Pack.git
cd Job-Pack
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
```
Edit `.env` with your values. **Never commit `.env` to git.**

### 4. Run
```bash
python app.py
```
Open [http://localhost:5001](http://localhost:5001) in your browser.

---

## Switching LLM backends

This app uses the **Strategy pattern** — changing backends requires **only** editing `.env`. Zero code changes.

| `LLM_BACKEND` | Description | Required env vars |
|---|---|---|
| `ollama` | Ollama Cloud (`ollama.com`) or self-hosted Ollama (default) | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` |
| `groq` | Groq free API (llama3, fast) | `GROQ_API_KEY`, `GROQ_MODEL` |
| `claude` | Anthropic Claude API | `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` |

The factory in `llm_strategy.py` reads `LLM_BACKEND` and returns the correct strategy object automatically.

---

## Sprint 2 — Messaging-Rich Architecture

Sprint 2 adds a messaging layer on top of the Sprint 1 generation pipeline: every
generation request is now driven by an explicit state machine, routed through a
content-based router, and broadcast in real time over WebSockets — with every
mutation logged to an append-only audit trail.

```
Frontend (static/index.html)
   │  POST /api/drafts            → create draft, get draft_id
   │  WS   join_draft {draft_id}  → subscribe to this draft's room
   │  POST /api/drafts/<id>/generate {regen_target}
   ▼
app.py
   │
   ├─ router.py          (Message Router)      picks which pipeline steps run
   ├─ state_machine.py    (State, GoF)          tracks workflow, publishes to bus
   ├─ pipeline.py         (Pipes-and-Filters)    runs the selected LLM/ATS steps
   │
   └─ event_bus.py        (Observer, GoF / Publish-Subscribe, EIP)
            │                              │
            ▼                              ▼
       sockets.py                     audit.py
       (WebSocket gateway,            (writes audit_log,
        emits to draft_<id> room)      never touches sockets.py)
```

`sockets.py` and `audit.py` never import each other or the state machine
directly — they only know about `event_bus.py`. That decoupling is the actual
point of Publish-Subscribe here, not just "we used WebSockets somewhere."

### Enterprise Integration Patterns (≥3, cited)

**1. Pipes and Filters** — [enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html)
`pipeline.py` — `Pipeline` chains named `Filter` callables (`resume → humanize → ats → cover_letter → company_fit`). Each filter receives the payload dict, transforms it, and passes it forward; `Pipeline.run()` threads the payload through whichever filters `router.py` selected. Carried over from Sprint 1, now with an `on_step` hook so the messaging layer can observe each step without the pipeline knowing messaging exists.

**2. Publish-Subscribe Channel** — [enterpriseintegrationpatterns.com/patterns/messaging/PublishSubscribeChannel.html](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PublishSubscribeChannel.html)
`event_bus.py` (broker) + `sockets.py` (WebSocket subscriber) + `audit.py` (persistence subscriber). Publishers (`state_machine.py`, `app.py`) call `bus.publish(event_name, **payload)`; subscribers register independently with `bus.subscribe(...)`. Transport is WebSockets via Flask-SocketIO, scoped per draft using Socket.IO rooms (`draft_<id>`) — multiple browser tabs/clients can join the same room and all receive the same events.

**3. Message Router** — [enterpriseintegrationpatterns.com/patterns/messaging/MessageRouter.html](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageRouter.html)
`router.py` — `route_request(regen_target)` is a content-based router: it inspects `regen_target` (`"full"`, `"resume"`, `"cover_letter"`, `"company_fit"`) and returns the ordered list of pipeline filter names to run. This is what lets the UI's "Regenerate" buttons re-run a single artifact instead of the whole pipeline.

### GoF Design Patterns (≥2)

**1. Strategy** — `llm_strategy.py`. Carried over from Sprint 1. `LLMStrategy` is the abstract interface; `OllamaStrategy`, `GroqStrategy`, `ClaudeStrategy` are concrete implementations; `get_llm_strategy()` is the factory.

**2. Builder** — `pdf_builder.py`. Carried over from Sprint 1. 10 concrete builders extend `PDFBuilder`, each producing a uniquely styled PDF.

**3. State** — `state_machine.py`. `DraftState` is the abstract state; `IdleState`, `ValidatingState`, `GeneratingStepState`, `AggregatingState`, `ReadyForReviewState`, `CompletedState`, `FailedState` are concrete states, each implementing `next(event, ctx)` to decide its own transitions (polymorphic dispatch, not an if/elif chain). `DraftContext` is the GoF Context — it holds the current state and the queue of steps the Message Router selected.

**4. Observer** — `event_bus.py`. `EventBus` is the Subject; anything that calls `bus.subscribe(event_name, handler)` (`sockets.py`, `audit.py`) is an Observer. **This is the same code that implements the Publish-Subscribe EIP above** — Observer is the object-design-level pattern, Publish-Subscribe is the integration-level pattern, and here they're literally the same class viewed at two abstraction levels.

### State chart

States, events, and guards for the generation workflow, implemented in `state_machine.py`:

```
IDLE → VALIDATING → GENERATING_RESUME → HUMANIZING_RESUME → SCORING_ATS
     → GENERATING_COVER_LETTER → GENERATING_COMPANY_FIT → AGGREGATING
     → READY_FOR_REVIEW → COMPLETED

(any GENERATING_*/AGGREGATING state) → FAILED
```

| From | Event | Guard | To |
|---|---|---|---|
| `IDLE` | `SUBMIT` | — | `VALIDATING` |
| `VALIDATING` | `VALIDATION_OK` | `job_description` and `candidate_profile` non-empty | next generating state (router-selected) |
| `VALIDATING` | `VALIDATION_FAILED` | — | `IDLE` |
| `GENERATING_*` / `SCORING_ATS` | `STEP_DONE` | — | next step in the Message Router's queue, or `AGGREGATING` if none left |
| `GENERATING_*` / `SCORING_ATS` / `AGGREGATING` | `ERROR` | — | `FAILED` |
| `AGGREGATING` | `AGGREGATE_DONE` | — | `READY_FOR_REVIEW` |
| `READY_FOR_REVIEW` | `USER_APPROVES` | — | `COMPLETED` |
| `READY_FOR_REVIEW` / `COMPLETED` | `REGENERATE` | — | `VALIDATING` |
| `FAILED` | `RETRY` | `retry_count < 3` | back to the state that failed |
| `FAILED` | `RETRY` | `retry_count >= 3` | `IDLE` |

Which generating states actually get visited (and in what order) is decided by `DraftContext._remaining_steps`, populated by `router.route_request()` — the State pattern handles the *shape* of the workflow, the Message Router decides its *content*.

### Audit trail / point-in-time reconstruction

Every state transition and pipeline step writes one row to `audit_log` (`database.py`):

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,   -- e.g. 'state_changed', 'step_complete:resume', 'downloaded'
    from_state TEXT,
    to_state TEXT,
    payload TEXT,               -- JSON snapshot of the field(s) that step actually wrote
    created_at TEXT NOT NULL
)
```

Each `step_complete:*` row's `payload` is a snapshot of the actual content that step
produced (the new `resume_text`, `ats_score`, `cover_letter_text`, or `company_fit` —
see `STEP_OUTPUT_FIELDS` in `pipeline.py`), not just the step's name and timestamp.
That's what makes **every mutation reconstructable**, not just orderable:

- `GET /api/drafts/<id>/audit` — full timeline, oldest first
- `GET /api/drafts/<id>/audit/reconstruct?as_of=<event_id>` — replays the log up to
  that event and rebuilds exactly what the draft's content looked like at that
  moment (`audit.py: reconstruct_draft_state`). Omit `as_of` to replay the full log
  as a check that it matches current state.

The `drafts` table stays the fast-read "current" view; `audit_log` is the
append-only source of truth you replay to answer "how did we get here."

### WebSocket events (`sockets.py`)

| Event | Payload | When |
|---|---|---|
| `state_changed` | `{draft_id, from_state, to_state}` | every state machine transition |
| `step_complete` | `{draft_id, step, result}` | each pipeline filter finishes |
| `generation_complete` | `{draft_id}` | `READY_FOR_REVIEW` reached |
| `generation_error` | `{draft_id, message}` | `FAILED` reached |

No polling: the frontend opens a Socket.IO connection, joins room `draft_<id>`, and
these events arrive while the `/generate` HTTP request is still in flight (verified —
all events for a ~38s real LLM run arrived live, not buffered until the response).

---

## Perfect Framework concerns addressed

| Concern | Implementation |
|---|---|
| **Secrets management** | All API keys in `.env`, excluded from git via `.gitignore`, never hardcoded |
| **Persistence** | SQLite (`drafts.db`) stores all drafts server-side — save, reopen, edit, compare |
| **Auditability** | `audit_log` table — append-only, every mutation timestamped and reconstructable (see above) |
| **Deployment** | Single-process Flask app with `Procfile` for Render; `eventlet.monkey_patch()` so blocking LLM calls don't freeze the WebSocket layer |
| **Auth** | Ollama Cloud endpoint uses `OLLAMA_API_KEY` via `Authorization: Bearer` header |

---

## Project structure

```
Job-Pack/
├── app.py            # Flask app, all API routes, wires the messaging layer together
├── llm_strategy.py   # Strategy (GoF) — LLM backends (Ollama, Groq, Claude)
├── pdf_builder.py     # Builder (GoF) — 10 PDF resume templates + cover letter
├── state_machine.py    # State (GoF) — DraftState classes + DraftContext
├── event_bus.py          # Observer (GoF) / Publish-Subscribe (EIP) broker
├── router.py               # Message Router (EIP) — selects pipeline steps from regen_target
├── pipeline.py               # Pipes-and-Filters (EIP) — generation + humanize + ATS scoring
├── sockets.py                  # WebSocket gateway (Flask-SocketIO), subscribes to event_bus
├── audit.py                     # Audit trail writer + reconstruct_draft_state(), subscribes to event_bus
├── infographic.py                # SVG company-fit infographic generator
├── database.py                     # SQLite persistence — drafts + audit_log tables
├── requirements.txt
├── Procfile
├── .env.example      # Copy to .env and fill in your values
├── .gitignore
└── static/
    └── index.html    # Single-page frontend (vanilla JS) + Socket.IO client
```

---

## Deploy to Render

1. Push to GitHub
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `python app.py`
5. Add your `.env` values as **Environment Variables** in the Render dashboard
   (note: `OLLAMA_BASE_URL` must be `https://ollama.com`, not `https://api.ollama.com`
   — the latter 301-redirects and most HTTP clients drop the auth header across that
   cross-host redirect)
6. Set `PORT=10000` (Render default)
