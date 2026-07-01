"""ArchaeoCode CLI."""
import argparse
from rich.console import Console
from rich.table import Table
from sqlalchemy import func

from archaeocode.extractor import RepoExtractor
from archaeocode.models import Commit, FileChange, get_session, get_engine
from archaeocode.ownership import OwnershipAnalyzer
from archaeocode.dependencies import DependencyGraphBuilder

console = Console()


def cmd_analyze(args):
    extractor = RepoExtractor(args.repo_path, args.db)
    console.print(f"[bold cyan]Excavating[/bold cyan] {args.repo_path} ...")
    count = extractor.extract_all(limit=args.limit)
    console.print(f"[bold green]Indexed {count} commits[/bold green] into {args.db}")
    _summary(args.db)


def cmd_ownership(args):
    engine = get_engine(args.db)
    session = get_session(engine)
    analyzer = OwnershipAnalyzer(session)

    dead = analyzer.get_dead_file_candidates()
    orphaned = analyzer.get_orphaned_files()

    table = Table(title=f"Top {args.top} Likely-Dead Files")
    table.add_column("File")
    table.add_column("Staleness")
    table.add_column("Created By")
    table.add_column("Current Owner")
    table.add_column("Days Since Touch")

    for f in dead[:args.top]:
        table.add_row(
            f.file_path,
            f"{f.staleness_score:.2f}",
            f.created_by,
            f.current_owner,
            str(f.days_since_last_touch),
        )
    console.print(table)
    console.print(f"\n[bold yellow]{len(orphaned)} orphaned files[/bold yellow]")
    session.close()


def cmd_deps(args):
    builder = DependencyGraphBuilder(args.repo_path)
    console.print(f"[bold cyan]Mapping dependencies[/bold cyan] in {args.repo_path} ...")
    graph = builder.build()
    console.print(f"[bold green]Parsed {len(graph)} Python files[/bold green]")

    if args.file:
        blast = builder.get_blast_radius(args.file)
        console.print(f"\n[bold]Blast radius for {args.file}:[/bold]")
        if not blast:
            console.print("  [yellow]Nothing in the repo imports this file[/yellow]")
        else:
            for dep in blast:
                console.print(f"  - {dep}")
        return

    orphans = builder.get_orphans()
    table = Table(title=f"Orphaned Files ({len(orphans)} found)")
    table.add_column("File")
    for path in orphans[:25]:
        table.add_row(path)
    console.print(table)


def _summary(db_path):
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


def main():
    parser = argparse.ArgumentParser(prog="archaeocode")
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Extract commit history from a repo")
    p_analyze.add_argument("repo_path")
    p_analyze.add_argument("--db", default="archaeocode.db")
    p_analyze.add_argument("--limit", type=int, default=None)

    # ownership
    p_own = sub.add_parser("ownership", help="Show dead files and ownership evolution")
    p_own.add_argument("--db", default="archaeocode.db")
    p_own.add_argument("--top", type=int, default=15)

    # deps
    p_deps = sub.add_parser("deps", help="Dependency graph and blast radius")
    p_deps.add_argument("repo_path")
    p_deps.add_argument("--file", default=None, help="Show blast radius for this file")

    args = parser.parse_args()
    {"analyze": cmd_analyze, "ownership": cmd_ownership, "deps": cmd_deps}[args.command](args)


if __name__ == "__main__":
    main()