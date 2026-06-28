"""
Audit trail — subscribes to the event bus and writes one row per event to
audit_log. Never imports state_machine.py or sockets.py directly; it only
knows about the bus, same as the WebSocket layer.

The drafts table stays the fast-read "current" view. audit_log is the
append-only mutation history you replay to reconstruct how a draft got here.
"""

from database import record_audit_event, get_audit_log
from event_bus import EventBus


def register_audit_subscriber(bus: EventBus) -> None:
    bus.subscribe("draft.state_changed", lambda **kw: record_audit_event(
        kw["draft_id"], "state_changed",
        from_state=kw.get("from_state"), to_state=kw.get("to_state"),
    ))
    bus.subscribe("draft.step_complete", lambda **kw: record_audit_event(
        kw["draft_id"], f"step_complete:{kw['step']}", payload=kw.get("result"),
    ))
    bus.subscribe("draft.generation_error", lambda **kw: record_audit_event(
        kw["draft_id"], "generation_error", payload={"message": kw.get("message")},
    ))
    bus.subscribe("draft.downloaded", lambda **kw: record_audit_event(
        kw["draft_id"], "downloaded", payload={"file": kw.get("file")},
    ))


def reconstruct_draft_timeline(draft_id: int) -> list[dict]:
    """Replay the audit log into a human-readable timeline, oldest first."""
    return get_audit_log(draft_id)


def reconstruct_draft_state(draft_id: int, as_of_event_id: int = None) -> dict:
    """
    Point-in-time reconstruction: replay audit_log events up to (and
    including) as_of_event_id and rebuild what the draft's content fields
    actually looked like at that moment. Omit as_of_event_id to replay the
    full log (i.e. the current state, derived purely from the audit trail
    rather than read from the drafts table).
    """
    state = {
        "current_state": "IDLE",
        "resume_text": None,
        "cover_letter_text": None,
        "ats_score": None,
        "company_fit": None,
        "as_of_event_id": as_of_event_id,
    }
    for event in get_audit_log(draft_id):
        if as_of_event_id is not None and event["id"] > as_of_event_id:
            break
        if event["event_type"] == "state_changed":
            state["current_state"] = event["to_state"]
        elif event["event_type"].startswith("step_complete:") and event.get("payload"):
            state.update(event["payload"])
    return state
