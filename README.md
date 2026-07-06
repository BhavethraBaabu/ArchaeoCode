# ArchaeoCode

> AI-powered codebase archaeology — reconstructs architecture timelines, ownership evolution, dependency history, and dead-code signals from a repo's git history.

Every codebase has files nobody understands — who wrote them, why they exist, what depends on them, whether they're safe to delete. ArchaeoCode mines git history to reconstruct that lost context automatically.

---

## Features

| Command | What it does |
|---|---|
| `analyze` | Index full commit + file-change history into SQLite |
| `ownership` | Ownership evolution, staleness scores, likely-dead files |
| `deps` | Direct dependency graph via AST import parsing |
| `blast` | Transitive blast radius — what breaks if you delete a file |
| `verdict` | Unified dead-file verdict (staleness + orphan + deps combined) |
| `timeline` | Architecture timeline — month-by-month file growth/shrink |
| `deleted` | Deleted features detector — files that lived then disappeared |
| `why` | NLP-classified commit intent history for any file |
| `intent` | Repo-wide commit intent distribution + most bug-prone files |
| `explain` | AI-generated archaeology report for a single file (Groq/Llama3.3) |
| `explain-repo` | AI summaries for top N most critical files |

---

## Install

```bash
git clone https://github.com/BhavethraBaabu/ArchaeoCode.git
cd ArchaeoCode
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### AI features (optional)
Get a free Groq API key at https://console.groq.com and add it to a `.env` file at the repo root:

```
GROQ_API_KEY=your_key_here
```

---

## Web app (Render)

Run locally:

```bash
uvicorn archaeocode.web:app --reload --port 8000
```

Open http://localhost:8000, paste a public GitHub repo URL, and get an HTML archaeology report.

### Deploy to Render

1. Push this repo to GitHub.
2. In [Render](https://render.com), click **New → Blueprint** and connect the repo (uses `render.yaml`),  
   **or** create a **Web Service** manually:
   - **Build:** `pip install -r requirements.txt && pip install -e .`
   - **Start:** `uvicorn archaeocode.web:app --host 0.0.0.0 --port $PORT`
3. No env vars required for the web report (AI `explain` commands are CLI-only).

Health check: `GET /health`
