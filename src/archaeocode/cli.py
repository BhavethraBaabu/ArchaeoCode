"""ArchaeoCode CLI — Day 1: raw history extraction."""
import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func

from archaeocode.extractor import RepoExtractor
from archaeocode.models import Commit, FileChange, get_session

app = typer.Typer()
console = Console()


@app.command()
def analyze(
    repo_path: str = typer.Argument(..., help="Path to the local git repo to analyze"),
    db_path: str = typer.Option("archaeocode.db", help="Output SQLite db path"),
    limit: int = typer.Option(None, help="Limit number of commits (for quick tests)"),
):
    """Extract full commit + file-change history from REPO_PATH."""
    extractor = RepoExtractor(repo_path, db_path)
    console.print(f"[bold cyan]Excavating[/bold cyan] {repo_path} ...")
    count = extractor.extract_all(limit=limit)
    console.print(f"[bold green]✓ Indexed {count} commits[/bold green] into {db_path}")
    _summary(db_path)


def _summary(db_path: str):
    from archaeocode.models import get_engine
    engine = get_engine(db_path)
    session = get_session(engine)

    total_commits = session.query(func.count(Commit.id)).scalar()
    total_files = session.query(func.count(func.distinct(FileChange.file_path))).scalar()

    top_authors = (
        session.query(Commit.author_name, func.count(Commit.id).label("n"))
        .group_by(Commit.author_name)
        .order_by(func.count(Commit.id).desc())
        .limit(5)
        .all()
    )

    table = Table(title="Archaeology Summary")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Total commits", str(total_commits))
    table.add_row("Distinct files touched", str(total_files))
    console.print(table)

    author_table = Table(title="Top Contributors")
    author_table.add_column("Author")
    author_table.add_column("Commits")
    for name, n in top_authors:
        author_table.add_row(name, str(n))
    console.print(author_table)

    session.close()


if __name__ == "__main__":
    app()