"""ArchaeoCode web app — analyze public GitHub repos in the browser."""
import html
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import git
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from archaeocode.extractor import RepoExtractor
from archaeocode.reporter import generate_report

WEB_DIR = Path(__file__).resolve().parent
COMMIT_LIMIT = 300
GITHUB_HOSTS = {"github.com", "www.github.com"}

app = FastAPI(title="ArchaeoCode", description="AI-powered codebase archaeology")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")


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


def run_analysis(github_url: str) -> str:
    clone_url = normalize_github_url(github_url)
    tmp = tempfile.mkdtemp(prefix="archaeocode_")
    try:
        repo_dir = Path(tmp) / "repo"
        db_path = Path(tmp) / "archaeocode.db"
        report_path = Path(tmp) / "report.html"

        git.Repo.clone_from(clone_url, repo_dir, depth=COMMIT_LIMIT + 50)
        RepoExtractor(str(repo_dir), str(db_path)).extract_all(limit=COMMIT_LIMIT)
        generate_report(str(repo_dir), str(db_path), str(report_path))
        return report_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyze", response_class=HTMLResponse)
def analyze(request: Request, github_url: str = Form(...)):
    try:
        report_html = run_analysis(github_url)
        return HTMLResponse(report_html)
    except ValueError as exc:
        message = str(exc)
        status_code = 400
    except git.exc.GitCommandError:
        message = (
            "Could not clone that repository. Make sure the URL is correct, "
            "the repo is public, and GitHub is reachable."
        )
        status_code = 400
    except Exception as exc:
        message = f"Something went wrong during analysis: {exc}"
        status_code = 500

    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "message": html.escape(message),
        },
        status_code=status_code,
    )
