"""
Database layer — SQLite via sqlite3 (no ORM needed for single-user app).
Handles draft persistence: save, list, load, update.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "drafts.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title   TEXT    NOT NULL DEFAULT 'Untitled',
                job_description  TEXT NOT NULL,
                candidate_profile TEXT NOT NULL,
                resume_text TEXT,
                cover_letter_text TEXT,
                company_fit TEXT,   -- JSON string
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


def save_draft(job_description: str, candidate_profile: str,
               resume_text: str = "", cover_letter_text: str = "",
               company_fit: dict = None, job_title: str = "Untitled") -> int:
    """Insert a new draft and return its ID."""
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO drafts
               (job_title, job_description, candidate_profile,
                resume_text, cover_letter_text, company_fit,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (job_title, job_description, candidate_profile,
             resume_text, cover_letter_text,
             json.dumps(company_fit) if company_fit else None,
             now, now)
        )
        conn.commit()
        return cur.lastrowid


def update_draft(draft_id: int, **kwargs):
    """Update any subset of fields on an existing draft."""
    allowed = {
        "job_title", "job_description", "candidate_profile",
        "resume_text", "cover_letter_text", "company_fit"
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if "company_fit" in fields and isinstance(fields["company_fit"], dict):
        fields["company_fit"] = json.dumps(fields["company_fit"])
    if not fields:
        return

    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [draft_id]

    with get_conn() as conn:
        conn.execute(f"UPDATE drafts SET {set_clause} WHERE id=?", values)
        conn.commit()


def list_drafts() -> list[dict]:
    """Return all drafts ordered by newest first (summary only)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, job_title, created_at, updated_at FROM drafts ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_draft(draft_id: int) -> dict | None:
    """Return a single draft by ID, or None if not found."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("company_fit"):
        d["company_fit"] = json.loads(d["company_fit"])
    return d


def delete_draft(draft_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
        conn.commit()
