"""
LLM Pipeline — Enterprise Integration Pattern: Pipes and Filters
Each 'filter' is a callable that transforms the payload dict.
Filters are composed into a pipeline and executed in sequence.
"""

from typing import Callable, Dict, Any
from llm_strategy import LLMStrategy
import re
import json as _json


# ── Filter type alias ────────────────────────────────────────────────────────

Filter = Callable[[Dict[str, Any]], Dict[str, Any]]


# ── Individual Filters ───────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Remove black square artifacts and other junk characters the LLM emits."""
    # ■ and □ used by some models as bullet/separator artifacts
    text = text.replace('■', '-').replace('□', '')
    # Other common artifacts
    text = text.replace('■', '-').replace('□', '')
    text = text.replace('�', '')
    return text


def validate_inputs(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Filter 1 — Ensure required fields are present."""
    required = ("job_description", "candidate_profile")
    for field in required:
        if not payload.get(field, "").strip():
            raise ValueError(f"Missing required field: {field}")
    return payload


def generate_resume(llm: LLMStrategy) -> Filter:
    """Filter 2 — Generate a customized résumé."""
    def _filter(payload: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "You are an expert resume writer. "
            "Given a job description and a candidate profile, produce a polished, "
            "ATS-optimized résumé in plain text. Use sections: Summary, Experience, "
            "Skills, Education. Tailor every bullet to the job description keywords. "
            "Start with the candidate's full name on the first line, then contact info."
        )
        user = (
            f"JOB DESCRIPTION:\n{payload['job_description']}\n\n"
            f"CANDIDATE PROFILE:\n{payload['candidate_profile']}\n\n"
            "Write the tailored résumé now."
        )
        payload["resume_text"] = _clean_text(llm.generate(system, user))
        return payload
    return _filter


def humanize_resume(llm: LLMStrategy) -> Filter:
    """Filter 3 — Make the résumé more human, less robotic. From filtered out to standout."""
    def _filter(payload: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "You are a professional resume editor who specializes in making resumes "
            "feel authentic, compelling, and human — not generic AI-generated filler. "
            "Your job: take the draft résumé and improve it so it stands out to BOTH "
            "ATS systems AND human hiring managers. "
            "Rules: "
            "1. Keep all factual information exactly as-is (dates, companies, titles). "
            "2. Replace generic phrases ('responsible for', 'worked on', 'helped with') "
            "   with strong, specific, active verbs. "
            "3. Add or sharpen quantifiable achievements (%, $, time saved, team size). "
            "4. Make the Summary sound like a real person wrote it — confident, specific, "
            "   not a list of buzzwords. "
            "5. Keep the same section structure and plain text format. "
            "Return ONLY the improved résumé text — no commentary."
        )
        user = (
            f"JOB DESCRIPTION (for context):\n{payload['job_description']}\n\n"
            f"DRAFT RÉSUMÉ TO IMPROVE:\n{payload['resume_text']}\n\n"
            "Return the improved, human-sounding résumé now."
        )
        payload["resume_text"] = _clean_text(llm.generate(system, user))
        return payload
    return _filter


def score_ats(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Filter 4 — Compute ATS keyword match score (no LLM needed, pure text analysis)."""
    job = payload.get("job_description", "").lower()
    resume = payload.get("resume_text", "").lower()

    # Extract meaningful keywords from job description (skip stop words)
    stop = {"the","a","an","and","or","but","in","on","at","to","for","of","with",
            "is","are","was","were","be","been","have","has","will","that","this",
            "we","you","our","your","their","as","by","from","about","up","out",
            "who","what","how","all","can","may","must","should","would","also",
            "its","it","they","them","these","those","than","then","when","where"}

    # Pull keywords from job: words 4+ chars, not stop words
    job_words = re.findall(r'\b[a-z][a-z0-9\+\#\.]{3,}\b', job)
    job_keywords = [w for w in job_words if w not in stop]

    # Deduplicate and count
    keyword_counts = {}
    for w in job_keywords:
        keyword_counts[w] = keyword_counts.get(w, 0) + 1

    # Top 30 most frequent keywords = the important ones
    top_keywords = sorted(keyword_counts, key=keyword_counts.get, reverse=True)[:30]

    matched = [k for k in top_keywords if k in resume]
    missing = [k for k in top_keywords if k not in resume]

    score = round((len(matched) / len(top_keywords)) * 100) if top_keywords else 0

    # Grade
    if score >= 80:   grade, label = "A", "Excellent"
    elif score >= 65: grade, label = "B", "Good"
    elif score >= 50: grade, label = "C", "Fair"
    else:             grade, label = "D", "Needs Work"

    payload["ats_score"] = {
        "score": score,
        "grade": grade,
        "label": label,
        "matched": matched[:12],
        "missing": missing[:8],
        "total_checked": len(top_keywords),
    }
    return payload


def generate_cover_letter(llm: LLMStrategy) -> Filter:
    """Filter 5 — Generate a customized cover letter."""
    def _filter(payload: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "You are an expert cover letter writer. "
            "Produce a professional, enthusiastic cover letter addressed to the company. "
            "Keep it to three paragraphs: hook, evidence, close. "
            "Sound like a real human — warm, confident, specific. Not a template."
        )
        user = (
            f"JOB DESCRIPTION:\n{payload['job_description']}\n\n"
            f"CANDIDATE PROFILE:\n{payload['candidate_profile']}\n\n"
            "Write the cover letter now. Address it to 'Hiring Manager' if no name is given."
        )
        payload["cover_letter_text"] = _clean_text(llm.generate(system, user))
        return payload
    return _filter


def generate_company_fit(llm: LLMStrategy) -> Filter:
    """Filter 6 — Generate pros/cons data for the infographic."""
    def _filter(payload: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "You are a career coach. Analyze the job description and candidate profile. "
            "Return ONLY valid JSON with these exact keys: "
            "'company_name' (string), "
            "'role_title' (string), "
            "'pros' (list of 4 short strings — reasons this is a good fit), "
            "'cons' (list of 4 short strings — gaps or concerns), "
            "'fit_score' (integer 1-10), "
            "'advice' (string — 2-3 sentences of honest, specific career coaching advice "
            "for this candidate applying to this role: what to highlight, what to address, "
            "and one actionable tip). "
            "No explanation, no markdown — raw JSON only."
        )
        user = (
            f"JOB DESCRIPTION:\n{payload['job_description']}\n\n"
            f"CANDIDATE PROFILE:\n{payload['candidate_profile']}"
        )
        raw = llm.generate(system, user)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        payload["company_fit"] = _json.loads(raw.strip())
        return payload
    return _filter


# ── Pipeline runner ──────────────────────────────────────────────────────────

class Pipeline:
    """
    Pipes-and-Filters pipeline.
    Add filters in order; run() threads the payload through each one.
    """

    def __init__(self):
        self._filters: list[Filter] = []

    def add(self, f: Filter) -> "Pipeline":
        self._filters.append(f)
        return self  # fluent API

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        for f in self._filters:
            payload = f(payload)
        return payload


def build_pipeline(llm: LLMStrategy) -> Pipeline:
    """Construct the standard generation pipeline."""
    return (
        Pipeline()
        .add(validate_inputs)
        .add(generate_resume(llm))
        .add(humanize_resume(llm))   # Makes resume human & standout
        .add(score_ats)              # ATS keyword scoring (no LLM)
        .add(generate_cover_letter(llm))
        .add(generate_company_fit(llm))
    )
