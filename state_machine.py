"""
GoF State pattern — models the draft generation workflow as explicit state
objects instead of control flow scattered across app.py.

DraftContext holds the current DraftState. Each state decides, by itself,
what event moves it to which next state — polymorphic dispatch, not one big
if/elif chain. Which generation step comes next is decided by the context's
step queue (populated by the Message Router in router.py), so the states
themselves don't need to know about regen_target.
"""

from abc import ABC, abstractmethod

from event_bus import EventBus

# Maps a pipeline filter name (router.py output) to the state that represents
# "this step is currently running".
STEP_TO_STATE_NAME = {
    "resume": "GENERATING_RESUME",
    "humanize": "HUMANIZING_RESUME",
    "ats": "SCORING_ATS",
    "cover_letter": "GENERATING_COVER_LETTER",
    "company_fit": "GENERATING_COMPANY_FIT",
}


class DraftState(ABC):
    name: str = "BASE"

    def on_enter(self, ctx: "DraftContext", from_state: str) -> None:
        ctx.bus.publish(
            "draft.state_changed",
            draft_id=ctx.draft_id,
            from_state=from_state,
            to_state=self.name,
        )

    @abstractmethod
    def next(self, event: str, ctx: "DraftContext") -> "DraftState":
        ...


class IdleState(DraftState):
    name = "IDLE"

    def next(self, event, ctx):
        if event == "SUBMIT":
            return ValidatingState()
        return self


class ValidatingState(DraftState):
    name = "VALIDATING"

    def next(self, event, ctx):
        if event == "VALIDATION_OK":
            return ctx.next_generating_state()
        if event == "VALIDATION_FAILED":
            return IdleState()
        return self


class GeneratingStepState(DraftState):
    """Represents 'currently running pipeline step <name>'. Which step comes
    next is decided by ctx.next_generating_state(), not hardcoded here —
    that's how this state stays agnostic to the Message Router's choices."""

    def __init__(self, name: str):
        self.name = name

    def next(self, event, ctx):
        if event == "STEP_DONE":
            return ctx.next_generating_state()
        if event == "ERROR":
            return FailedState(previous=self)
        return self


class AggregatingState(DraftState):
    name = "AGGREGATING"

    def next(self, event, ctx):
        if event == "AGGREGATE_DONE":
            return ReadyForReviewState()
        if event == "ERROR":
            return FailedState(previous=self)
        return self


class ReadyForReviewState(DraftState):
    name = "READY_FOR_REVIEW"

    def next(self, event, ctx):
        if event == "USER_APPROVES":
            return CompletedState()
        if event == "REGENERATE":
            return ValidatingState()
        return self


class CompletedState(DraftState):
    name = "COMPLETED"

    def next(self, event, ctx):
        if event == "REGENERATE":
            return ValidatingState()
        return self


class FailedState(DraftState):
    name = "FAILED"

    def __init__(self, previous: DraftState):
        self.previous = previous

    def next(self, event, ctx):
        if event == "RETRY" and ctx.retry_count < 3:
            ctx.retry_count += 1
            return self.previous
        if event == "RETRY":
            return IdleState()
        return self


class DraftContext:
    """The GoF 'Context' — holds the current state plus the queue of steps
    the Message Router selected for this request."""

    def __init__(self, draft_id: int, bus: EventBus, step_names: list[str]):
        self.draft_id = draft_id
        self.bus = bus
        self.retry_count = 0
        self._remaining_steps = list(step_names)
        self.state: DraftState = IdleState()

    def next_generating_state(self) -> DraftState:
        if self._remaining_steps:
            step_name = self._remaining_steps.pop(0)
            return GeneratingStepState(STEP_TO_STATE_NAME[step_name])
        return AggregatingState()

    def handle(self, event: str) -> DraftState:
        from_state = self.state.name
        new_state = self.state.next(event, self)
        if new_state is not self.state:
            self.state = new_state
            self.state.on_enter(self, from_state)
        return self.state
