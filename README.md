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
