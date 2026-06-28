"""
Manifest — Flask application entry point.
Perfect Framework concerns addressed:
  - Secrets management: all keys loaded from .env, never hardcoded
  - Persistence: SQLite draft storage via database.py
  - Deploy: single-process app, Procfile included for cloud deploy
"""

# Must happen before any other import (especially `requests`/`socket`) —
# without this, a blocking LLM HTTP call freezes eventlet's entire event
# loop and the WebSocket layer can't service any other connection while
# generation is in flight.
import eventlet
eventlet.monkey_patch()

import os
import json
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import io

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from database import init_db, save_draft, update_draft, list_drafts, get_draft, delete_draft
from llm_strategy import get_llm_strategy
from pipeline import build_pipeline, validate_inputs, STEP_OUTPUT_FIELDS
from pdf_builder import build_resume_pdf, build_cover_letter_pdf, TEMPLATES
from infographic import generate_infographic_svg
from event_bus import bus
from router import route_request
from state_machine import DraftContext
from sockets import init_socketio, register_socket_subscribers
from audit import register_audit_subscriber, reconstruct_draft_timeline, reconstruct_draft_state

app = Flask(__name__, static_folder="static")
CORS(app)  # Allow Netlify frontend to call this backend
socketio = init_socketio(app)

# Initialize DB on startup
init_db()

# Wire the messaging layer once at startup: WebSocket gateway and audit
# trail both subscribe to the same bus, and never talk to each other.
register_socket_subscribers(bus)
register_audit_subscriber(bus)


# ── Health check ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    backend = os.getenv("LLM_BACKEND", "ollama")
    return jsonify({"status": "ok", "llm_backend": backend})


# ── Resume templates list ────────────────────────────────────────────────────

@app.route("/api/templates")
def list_templates():
    return jsonify([
        {"id": k, "name": v[0], "description": v[1]}
        for k, v in TEMPLATES.items()
    ])


# ── File upload → extract text ────────────────────────────────────────────────

@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    """
    Accept a PDF, DOCX, or TXT file and return its extracted plain text.
    The frontend pastes this text into the candidate profile field.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    filename = f.filename.lower()

    try:
        if filename.endswith(".txt"):
            text = f.read().decode("utf-8", errors="ignore")

        elif filename.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(f) as pdf:
                text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )

        elif filename.endswith(".docx"):
            from docx import Document
            doc = Document(f)
            text = "\n".join(p.text for p in doc.paragraphs)

        else:
            return jsonify({"error": "Unsupported file type. Use PDF, DOCX, or TXT."}), 400

        text = text.strip()
        if not text:
            return jsonify({"error": "Could not extract text from the file."}), 400

        return jsonify({"text": text})

    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500


# ── Generation ───────────────────────────────────────────────────────────────

@app.route("/api/drafts", methods=["POST"])
def create_draft():
    """
    Create a placeholder draft and return its ID immediately, before any
    generation runs. The frontend joins the draft's WebSocket room with this
    ID, then calls /api/drafts/<id>/generate — that's what lets it watch
    real-time progress on a request that hasn't been made yet.
    """
    data = request.get_json(force=True)
    job_description = data.get("job_description", "").strip()
    candidate_profile = data.get("candidate_profile", "").strip()
    job_title = data.get("job_title", "Untitled Job").strip()

    if not job_description or not candidate_profile:
        return jsonify({"error": "job_description and candidate_profile are required"}), 400

    draft_id = save_draft(
        job_description=job_description,
        candidate_profile=candidate_profile,
        job_title=job_title,
    )
    return jsonify({"draft_id": draft_id})


@app.route("/api/drafts/<int:draft_id>/generate", methods=["POST"])
def generate_draft(draft_id):
    """
    Run the generation pipeline against an existing draft.
    Body: {"regen_target": "full" | "resume" | "cover_letter" | "company_fit"}
    Message Router (router.py) picks which pipeline steps run; the State
    pattern (state_machine.py) tracks workflow progress and publishes
    state_changed/step_complete events on the bus, which sockets.py and
    audit.py each independently subscribe to.
    """
    draft = get_draft(draft_id)
    if draft is None:
        return jsonify({"error": "Draft not found"}), 404

    data = request.get_json(force=True) or {}
    regen_target = data.get("regen_target", "full")

    try:
        filter_names = route_request(regen_target)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    ctx = DraftContext(draft_id, bus, filter_names)
    ctx.handle("SUBMIT")  # IDLE -> VALIDATING

    payload = {
        "draft_id": draft_id,
        "job_description": draft["job_description"],
        "candidate_profile": draft["candidate_profile"],
        "resume_text": draft.get("resume_text") or "",
        "cover_letter_text": draft.get("cover_letter_text") or "",
    }

    try:
        validate_inputs(payload)
    except ValueError as e:
        ctx.handle("VALIDATION_FAILED")
        return jsonify({"error": str(e)}), 400
    ctx.handle("VALIDATION_OK")  # VALIDATING -> first generating step

    def on_step(step_name, step_payload):
        # Snapshot the field(s) this step actually wrote, so the audit log
        # captures the resulting content per mutation, not just its name —
        # that's what makes a draft's state at any past point reconstructable.
        snapshot = {f: step_payload.get(f) for f in STEP_OUTPUT_FIELDS.get(step_name, [])}
        bus.publish("draft.step_complete", draft_id=draft_id, step=step_name, result=snapshot)
        ctx.handle("STEP_DONE")

    try:
        llm = get_llm_strategy()
        pipeline = build_pipeline(llm, filter_names)
        payload = pipeline.run(payload, on_step=on_step)
        ctx.handle("AGGREGATE_DONE")  # AGGREGATING -> READY_FOR_REVIEW
    except Exception as e:
        bus.publish("draft.generation_error", draft_id=draft_id, message=str(e))
        ctx.handle("ERROR")
        update_draft(draft_id, current_state=ctx.state.name)
        return jsonify({"error": str(e)}), 500

    update_draft(
        draft_id,
        resume_text=payload.get("resume_text", draft.get("resume_text", "")),
        cover_letter_text=payload.get("cover_letter_text", draft.get("cover_letter_text", "")),
        company_fit=payload.get("company_fit", draft.get("company_fit")),
        ats_score=payload.get("ats_score", draft.get("ats_score")),
        current_state=ctx.state.name,
    )
    bus.publish("draft.generation_complete", draft_id=draft_id)

    return jsonify({
        "draft_id": draft_id,
        "resume_text": payload.get("resume_text", ""),
        "cover_letter_text": payload.get("cover_letter_text", ""),
        "company_fit": payload.get("company_fit", draft.get("company_fit") or {}),
        "ats_score": payload.get("ats_score", draft.get("ats_score") or {}),
    })


@app.route("/api/drafts/<int:draft_id>/audit")
def get_draft_audit(draft_id):
    """Timestamped mutation history for a draft."""
    return jsonify(reconstruct_draft_timeline(draft_id))


@app.route("/api/drafts/<int:draft_id>/audit/reconstruct")
def reconstruct_draft(draft_id):
    """
    Point-in-time reconstruction. ?as_of=<audit_log id> rebuilds exactly
    what the draft's content looked like right after that event, derived
    purely by replaying audit_log — not by reading the drafts table.
    Omit as_of to reconstruct the current state the same way, as a check
    that replay matches what's actually stored.
    """
    as_of = request.args.get("as_of", type=int)
    return jsonify(reconstruct_draft_state(draft_id, as_of_event_id=as_of))


@app.route("/api/drafts/<int:draft_id>/state")
def get_draft_state(draft_id):
    draft = get_draft(draft_id)
    if draft is None:
        return jsonify({"error": "Draft not found"}), 404
    return jsonify({"state": draft.get("current_state", "IDLE")})


# ── Draft CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/drafts", methods=["GET"])
def list_all_drafts():
    return jsonify(list_drafts())


@app.route("/api/drafts/<int:draft_id>", methods=["GET"])
def get_one_draft(draft_id):
    draft = get_draft(draft_id)
    if draft is None:
        return jsonify({"error": "Draft not found"}), 404
    return jsonify(draft)


@app.route("/api/drafts/<int:draft_id>", methods=["PUT"])
def update_one_draft(draft_id):
    data = request.get_json(force=True)
    allowed = {"job_title", "job_description", "candidate_profile",
                "resume_text", "cover_letter_text"}
    updates = {k: v for k, v in data.items() if k in allowed}
    update_draft(draft_id, **updates)
    return jsonify({"status": "updated"})


@app.route("/api/drafts/<int:draft_id>", methods=["DELETE"])
def delete_one_draft(draft_id):
    delete_draft(draft_id)
    return jsonify({"status": "deleted"})


# ── PDF Downloads ─────────────────────────────────────────────────────────────

@app.route("/api/drafts/<int:draft_id>/resume.pdf")
def download_resume(draft_id):
    draft = get_draft(draft_id)
    if not draft or not draft.get("resume_text"):
        return jsonify({"error": "No resume found for this draft"}), 404
    template = request.args.get("template", "classic")
    pdf_bytes = build_resume_pdf(draft["resume_text"], template=template)
    bus.publish("draft.downloaded", draft_id=draft_id, file="resume.pdf")
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resume_{template}_draft_{draft_id}.pdf",
    )


@app.route("/api/drafts/<int:draft_id>/cover_letter.pdf")
def download_cover_letter(draft_id):
    draft = get_draft(draft_id)
    if not draft or not draft.get("cover_letter_text"):
        return jsonify({"error": "No cover letter found for this draft"}), 404
    template = request.args.get("template", "classic")
    name = request.args.get("name", "")
    contact = request.args.get("contact", "")
    pdf_bytes = build_cover_letter_pdf(
        draft["cover_letter_text"], template=template, name=name, contact=contact)
    bus.publish("draft.downloaded", draft_id=draft_id, file="cover_letter.pdf")
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"cover_letter_{template}_draft_{draft_id}.pdf",
    )


@app.route("/api/drafts/<int:draft_id>/infographic.svg")
def download_infographic(draft_id):
    draft = get_draft(draft_id)
    if not draft or not draft.get("company_fit"):
        return jsonify({"error": "No infographic data for this draft"}), 404
    svg = generate_infographic_svg(draft["company_fit"])
    return send_file(
        io.BytesIO(svg.encode("utf-8")),
        mimetype="image/svg+xml",
        as_attachment=True,
        download_name=f"company_fit_draft_{draft_id}.svg",
    )


# ── Serve frontend (when running as single process) ───────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
