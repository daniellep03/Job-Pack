"""
WebSocket gateway — EIP Publish-Subscribe transport.

Subscribes to the event bus and forwards events to the browser over
Socket.IO, scoped per draft via rooms. Never called directly by the
pipeline or state machine — fully decoupled through event_bus.py.
"""

from flask_socketio import SocketIO, join_room

from event_bus import EventBus

# async_mode="threading" uses real OS threads via Werkzeug's threaded dev
# server instead of eventlet's monkey-patched green threads. Plenty for this
# app's concurrency needs (one demo, a handful of viewers) and it avoids
# eventlet's monkey-patching landmines entirely (e.g. "RLock(s) were not
# greened" when something in the host environment creates a lock before
# monkey_patch() runs — that's what caused production 502s under eventlet).
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def init_socketio(app):
    socketio.init_app(app)

    @socketio.on("join_draft")
    def handle_join(data):
        draft_id = data.get("draft_id")
        if draft_id is not None:
            join_room(f"draft_{draft_id}")

    return socketio


def register_socket_subscribers(bus: EventBus) -> None:
    bus.subscribe("draft.state_changed", lambda **kw: socketio.emit(
        "state_changed", kw, room=f"draft_{kw['draft_id']}"))
    bus.subscribe("draft.step_complete", lambda **kw: socketio.emit(
        "step_complete", kw, room=f"draft_{kw['draft_id']}"))
    bus.subscribe("draft.generation_complete", lambda **kw: socketio.emit(
        "generation_complete", kw, room=f"draft_{kw['draft_id']}"))
    bus.subscribe("draft.generation_error", lambda **kw: socketio.emit(
        "generation_error", kw, room=f"draft_{kw['draft_id']}"))
