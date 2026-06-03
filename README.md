# Manifest — AI Job Application Generator

> *Transforming potential into opportunity.*

Paste a job description + your profile → get a tailored résumé PDF, cover letter PDF, and company-fit infographic — powered by AI.

**Live demo:** *(add your Render URL here after deploying)*

---

## What it does

- **Tailored Résumé** — ATS-optimized, humanized, keyword-matched to the job description
- **Cover Letter** — Three-paragraph, professional, addressed to the company
- **Company Fit Report** — Pros/cons + fit score + career coach advice
- **ATS Score** — Keyword match % with matched/missing keywords shown
- **10 Resume Templates** — Classic, Modern Tech, Multicolumn, Minimalist, Executive Banner, Bold Header, Split Column, Simple Sidebar, Professional, Compact Pro
- **Draft Management** — Save, reopen, edit inline, and compare ≥2 drafts
- **File Upload** — Upload PDF, DOCX, or TXT résumé instead of pasting

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
| `ollama` | Hosted class Ollama or local Ollama (default) | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` |
| `groq` | Groq free API (llama3, fast) | `GROQ_API_KEY`, `GROQ_MODEL` |
| `claude` | Anthropic Claude API | `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` |

The factory in `llm_strategy.py` reads `LLM_BACKEND` and returns the correct strategy object automatically.

---

## Design patterns used

### 1. Strategy (GoF) — `llm_strategy.py`
`LLMStrategy` is the abstract interface. `OllamaStrategy`, `GroqStrategy`, and `ClaudeStrategy` are concrete implementations. `get_llm_strategy()` is the factory. Swapping backends = changing one env var.

### 2. Builder (GoF) — `pdf_builder.py`
10 concrete builders extend `PDFBuilder` (e.g. `ClassicBuilder`, `ModernTechBuilder`, `ExecutiveBannerBuilder`). Each builds a uniquely styled PDF independently, separating construction logic from representation.

### 3. Pipes and Filters (Enterprise Integration Pattern) — `pipeline.py`
`Pipeline` chains `Filter` callables. Each filter receives a payload dict, transforms it, and passes it forward:
`validate → generate_resume → humanize_resume → score_ats → generate_cover_letter → generate_company_fit`

---

## Perfect Framework concerns addressed

| Concern | Implementation |
|---|---|
| **Secrets management** | All API keys in `.env`, excluded from git via `.gitignore`, never hardcoded |
| **Persistence** | SQLite (`drafts.db`) stores all drafts server-side — save, reopen, edit, compare |
| **Deployment** | Single-process Flask app with `Procfile` for Render |
| **Auth** | Class Ollama endpoint uses `OLLAMA_API_KEY` via `Authorization: Bearer` header |

---

## Project structure

```
Job-Pack/
├── app.py            # Flask app, all API routes
├── llm_strategy.py   # Strategy pattern — LLM backends (Ollama, Groq, Claude)
├── pipeline.py       # Pipes-and-Filters — generation + humanize + ATS scoring
├── pdf_builder.py    # Builder pattern — 10 PDF resume templates + cover letter
├── infographic.py    # SVG company-fit infographic generator
├── database.py       # SQLite draft persistence (CRUD)
├── requirements.txt
├── Procfile
├── .env.example      # Copy to .env and fill in your values
├── .gitignore
└── static/
    └── index.html    # Full single-page frontend (vanilla JS)
```

---

## Deploy to Render

1. Push to GitHub
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `python app.py`
5. Add your `.env` values as **Environment Variables** in the Render dashboard
6. Set `PORT=10000` (Render default)
