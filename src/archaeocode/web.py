"""FastAPI web app — paste a GitHub URL, get an archaeology HTML report."""
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import git
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from archaeocode.extractor import RepoExtractor
from archaeocode.reporter import generate_report_html

app = FastAPI(title="ArchaeoCode", description="AI-powered codebase archaeology")

GITHUB_HOSTS = {"github.com", "www.github.com"}
DEFAULT_COMMIT_LIMIT = 500
MAX_COMMIT_LIMIT = 3000

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ArchaeoCode</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0d1117; color: #c9d1d9; min-height: 100vh;
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 2rem;
  }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 12px;
    padding: 2.5rem; max-width: 560px; width: 100%;
  }
  h1 { color: #f0f6fc; font-size: 1.75rem; margin-bottom: 0.5rem; }
  h1 span { color: #58a6ff; }
  p { color: #8b949e; margin-bottom: 1.5rem; line-height: 1.6; }
  label { display: block; color: #8b949e; font-size: 0.85rem; margin-bottom: 0.4rem; }
  input[type="url"], input[type="number"] {
    width: 100%; padding: 0.75rem 1rem; border-radius: 6px;
    border: 1px solid #30363d; background: #0d1117; color: #f0f6fc;
    font-size: 1rem; margin-bottom: 1rem;
  }
  input:focus { outline: none; border-color: #58a6ff; }
  button {
    width: 100%; padding: 0.85rem; border: none; border-radius: 6px;
    background: #238636; color: #fff; font-size: 1rem; font-weight: 600;
    cursor: pointer;
  }
  button:hover { background: #2ea043; }
  .hint { font-size: 0.8rem; color: #6e7681; margin-top: 1rem; }
  .features { margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid #30363d; }
  .features li { color: #8b949e; font-size: 0.85rem; margin-left: 1.2rem; margin-bottom: 0.35rem; }
</style>
</head>
<body>
  <div class="card">
    <h1><span>Archaeo</span>Code</h1>
    <p>Paste a public GitHub repo URL. We clone it, mine the git history, and generate
       a full archaeology report — dead files, timelines, intent breakdown, and more.</p>
    <form action="/analyze" method="post">
      <label for="repo_url">GitHub repository URL</label>
      <input type="url" id="repo_url" name="repo_url"
             placeholder="https://github.com/owner/repo" required>
      <label for="limit">Max commits to analyze</label>
      <input type="number" id="limit" name="limit" value="500" min="50" max="3000">
      <button type="submit">Excavate repository</button>
    </form>
    <p class="hint">Public repos only. Analysis may take 30–90 seconds for large histories.</p>
    <ul class="features">
      <li>Dead-file verdicts and orphan detection</li>
      <li>Architecture timeline and deleted-feature history</li>
      <li>Commit intent classification (feature, bugfix, refactor…)</li>
    </ul>
  </div>
</body>
</html>"""


def _error_page(message: str) -> str:
    safe = re.sub(r"[<>]", "", message)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ArchaeoCode — Error</title>
<style>
  body {{ font-family: sans-serif; background: #0d1117; color: #c9d1d9;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; padding: 2rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
           padding: 2rem; max-width: 520px; }}
  h1 {{ color: #e74c3c; font-size: 1.25rem; margin-bottom: 1rem; }}
  p {{ color: #8b949e; margin-bottom: 1.5rem; }}
  a {{ color: #58a6ff; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Analysis failed</h1>
    <p>{safe}</p>
    <a href="/">← Try again</a>
  </div>
</body>
</html>"""


def normalize_github_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parsed = urlparse(url)
    if parsed.netloc.lower() not in GITHUB_HOSTS:
        raise ValueError("Only public github.com repository URLs are supported.")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL — use https://github.com/owner/repo")
    owner, repo = parts[0], parts[1]
    if not re.fullmatch(r"[\w.-]+", owner) or not re.fullmatch(r"[\w.-]+", repo):
        raise ValueError("Invalid GitHub URL format.")
    return f"https://github.com/{owner}/{repo}.git"


def run_analysis(repo_url: str, commit_limit: int) -> str:
    clone_url = normalize_github_url(repo_url)
    commit_limit = max(50, min(commit_limit, MAX_COMMIT_LIMIT))
    clone_depth = min(commit_limit + 50, MAX_COMMIT_LIMIT)

    tmp = tempfile.mkdtemp(prefix="archaeocode_")
    try:
        repo_dir = Path(tmp) / "repo"
        db_path = Path(tmp) / "archaeocode.db"
        git.Repo.clone_from(clone_url, repo_dir, depth=clone_depth)
        extractor = RepoExtractor(str(repo_dir), str(db_path))
        extractor.extract_all(limit=commit_limit)
        return generate_report_html(str(repo_dir), str(db_path))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    return LANDING_HTML


@app.post("/analyze", response_class=HTMLResponse)
def analyze(repo_url: str = Form(...), limit: int = Form(DEFAULT_COMMIT_LIMIT)):
    try:
        html = run_analysis(repo_url, limit)
        return HTMLResponse(html)
    except ValueError as exc:
        return HTMLResponse(_error_page(str(exc)), status_code=400)
    except git.exc.GitCommandError as exc:
        return HTMLResponse(
            _error_page(f"Could not clone repository: {exc}"),
            status_code=400,
        )
    except Exception as exc:
        return HTMLResponse(
            _error_page(f"Unexpected error: {exc}"),
            status_code=500,
        )
