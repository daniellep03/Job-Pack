"""
Manifest — Flask application entry point.
Perfect Framework concerns addressed:
  - Secrets management: all keys loaded from .env, never hardcoded
  - Persistence: SQLite draft storage via database.py
  - Deploy: single-process app, Procfile included for cloud deploy
"""

import os
import json
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import io

load_dotenv()  # Load .env before anything reads os.getenv

from database import init_db, save_draft, update_draft, list_drafts, get_draft, delete_draft
from llm_strategy import get_llm_strategy
from pipeline import build_pipeline
from pdf_builder import build_resume_pdf, build_cover_letter_pdf, TEMPLATES
from infographic import generate_infographic_svg

app = Flask(__name__, static_folder="static")
CORS(app)  # Allow Netlify frontend to call this backend

# Initialize DB on startup
init_db()


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

@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Accepts job_description + candidate_profile, runs the LLM pipeline,
    saves as a draft, and returns all generated text + draft ID.
    """
    data = request.get_json(force=True)
    job_description = data.get("job_description", "").strip()
    candidate_profile = data.get("candidate_profile", "").strip()
    job_title = data.get("job_title", "Untitled Job").strip()

    if not job_description or not candidate_profile:
        return jsonify({"error": "job_description and candidate_profile are required"}), 400

    try:
        llm = get_llm_strategy()
        pipeline = build_pipeline(llm)
        result = pipeline.run({
            "job_description": job_description,
            "candidate_profile": candidate_profile,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    draft_id = save_draft(
        job_description=job_description,
        candidate_profile=candidate_profile,
        resume_text=result.get("resume_text", ""),
        cover_letter_text=result.get("cover_letter_text", ""),
        company_fit=result.get("company_fit"),
        job_title=job_title,
    )

    return jsonify({
        "draft_id": draft_id,
        "resume_text": result.get("resume_text", ""),
        "cover_letter_text": result.get("cover_letter_text", ""),
        "company_fit": result.get("company_fit", {}),
        "ats_score": result.get("ats_score", {}),
    })


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
    app.run(host="0.0.0.0", port=port, debug=debug)
