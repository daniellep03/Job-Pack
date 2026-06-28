"""
Message Router — Enterprise Integration Pattern.

Decides which subset of the generation pipeline a request actually needs,
based on what the caller wants regenerated. This is what powers
"regenerate just the cover letter" instead of re-running everything (and
burning an extra LLM call on a résumé that was already fine).
"""

VALID_TARGETS = ("full", "resume", "cover_letter", "company_fit")


def route_request(regen_target: str = "full") -> list[str]:
    """Return the ordered list of pipeline filter names to run for this request."""
    regen_target = regen_target or "full"
    if regen_target not in VALID_TARGETS:
        raise ValueError(f"Unknown regen_target '{regen_target}'. Use one of {VALID_TARGETS}.")

    if regen_target == "full":
        return ["resume", "humanize", "ats", "cover_letter", "company_fit"]
    if regen_target == "resume":
        return ["resume", "humanize", "ats"]
    if regen_target == "cover_letter":
        return ["cover_letter"]
    return ["company_fit"]
