"""ArchaeoCode CLI."""
import argparse
from rich.console import Console
from rich.table import Table
from sqlalchemy import func

from archaeocode.extractor import RepoExtractor
from archaeocode.models import Commit, FileChange, get_session, get_engine
from archaeocode.ownership import OwnershipAnalyzer
from archaeocode.dependencies import DependencyGraphBuilder
from archaeocode.graph import TransitiveDependencyGraph, DeadFileAnalyzer
from archaeocode.timeline import TimelineAnalyzer

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
        direct = list(set(graph[args.file].imported_by)) if args.file in graph else []
        console.print(f"\n[bold]Direct blast radius for {args.file}:[/bold]")
        if not direct:
            console.print("  [yellow]Nothing imports this file[/yellow]")
        else:
            for f in direct:
                console.print(f"  - {f}")
        return

    orphans = builder.get_orphans()
    table = Table(title=f"Orphaned Files ({len(orphans)} found)")
    table.add_column("File")
    for path in orphans[:25]:
        table.add_row(path)
    console.print(table)


def cmd_blast(args):
    builder = DependencyGraphBuilder(args.repo_path)
    console.print(f"[bold cyan]Building transitive graph[/bold cyan] ...")
    graph = builder.build()
    tdg = TransitiveDependencyGraph(graph)
    report = tdg.transitive_blast_radius(args.file)

    console.print(f"\n[bold]Transitive blast radius for:[/bold] {args.file}")
    console.print(f"[bold red]Total affected: {report.total_affected} files[/bold red]")

    if report.direct_dependents:
        table = Table(title="Direct dependents (1 hop)")
        table.add_column("File")
        for f in sorted(set(report.direct_dependents)):
            table.add_row(f)
        console.print(table)

    if report.transitive_dependents:
        table = Table(title="Transitive dependents (2+ hops)")
        table.add_column("File")
        for f in sorted(set(report.transitive_dependents))[:20]:
            table.add_row(f)
        console.print(table)


def cmd_verdict(args):
    builder = DependencyGraphBuilder(args.repo_path)
    console.print(f"[bold cyan]Running full dead-file analysis[/bold cyan] ...")
    graph = builder.build()
    tdg = TransitiveDependencyGraph(graph)
    engine = get_engine(args.db)
    session = get_session(engine)
    analyzer = DeadFileAnalyzer(OwnershipAnalyzer(session), tdg, graph)
    dead = analyzer.get_dead()

    table = Table(title=f"Dead File Verdicts ({len(dead)} files)")
    table.add_column("Verdict")
    table.add_column("Conf")
    table.add_column("File")
    table.add_column("Days Idle")
    table.add_column("Orphan")
    table.add_column("Author Gone")
    for v in dead[:args.top]:
        color = "red" if v.verdict == "DEAD" else "yellow"
        table.add_row(
            f"[{color}]{v.verdict}[/{color}]",
            f"{v.confidence:.2f}",
            v.file_path,
            str(v.days_since_last_touch),
            "yes" if v.is_orphan else "no",
            "yes" if v.original_author_gone else "no",
        )
    console.print(table)
    session.close()


def cmd_timeline(args):
    engine = get_engine(args.db)
    session = get_session(engine)
    analyzer = TimelineAnalyzer(session)
    snapshots = analyzer.build_monthly_timeline()

    table = Table(title="Architecture Timeline (monthly)")
    table.add_column("Month")
    table.add_column("Commits")
    table.add_column("Added")
    table.add_column("Deleted")
    table.add_column("Modified")
    table.add_column("Net")
    table.add_column("Live Files")
    table.add_column("Top Author")

    for s in snapshots[-24:]:   # last 24 months by default
        net_color = "green" if s.net_change >= 0 else "red"
        table.add_row(
            s.year_month,
            str(s.commit_count),
            str(s.files_added),
            str(s.files_deleted),
            str(s.files_modified),
            f"[{net_color}]{s.net_change:+d}[/{net_color}]",
            str(s.cumulative_files),
            s.top_author[:20],
        )
    console.print(table)
    session.close()


def cmd_deleted(args):
    engine = get_engine(args.db)
    session = get_session(engine)
    analyzer = TimelineAnalyzer(session)
    deleted = analyzer.find_deleted_features(min_lifetime_days=args.min_days)

    table = Table(title=f"Deleted Features ({len(deleted)} found, lived >{args.min_days} days)")
    table.add_column("File")
    table.add_column("Module")
    table.add_column("Lifetime (days)")
    table.add_column("Created By")
    table.add_column("Deleted By")
    table.add_column("Created At")
    table.add_column("Deleted At")

    for f in deleted[:args.top]:
        table.add_row(
            f.file_path,
            f.module,
            str(f.lifetime_days),
            f.created_by[:18],
            f.deleted_by[:18],
            f.created_at.strftime("%Y-%m-%d"),
            f.deleted_at.strftime("%Y-%m-%d"),
        )
    console.print(table)
    session.close()


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

    p_analyze = sub.add_parser("analyze")
    p_analyze.add_argument("repo_path")
    p_analyze.add_argument("--db", default="archaeocode.db")
    p_analyze.add_argument("--limit", type=int, default=None)

    p_own = sub.add_parser("ownership")
    p_own.add_argument("--db", default="archaeocode.db")
    p_own.add_argument("--top", type=int, default=15)

    p_deps = sub.add_parser("deps")
    p_deps.add_argument("repo_path")
    p_deps.add_argument("--file", default=None)

    p_blast = sub.add_parser("blast")
    p_blast.add_argument("repo_path")
    p_blast.add_argument("--file", required=True)

    p_verdict = sub.add_parser("verdict")
    p_verdict.add_argument("repo_path")
    p_verdict.add_argument("--db", default="archaeocode.db")
    p_verdict.add_argument("--top", type=int, default=20)

    p_timeline = sub.add_parser("timeline")
    p_timeline.add_argument("--db", default="archaeocode.db")

    p_deleted = sub.add_parser("deleted")
    p_deleted.add_argument("--db", default="archaeocode.db")
    p_deleted.add_argument("--min-days", type=int, default=30)
    p_deleted.add_argument("--top", type=int, default=20)

    args = parser.parse_args()
    {
        "analyze": cmd_analyze,
        "ownership": cmd_ownership,
        "deps": cmd_deps,
        "blast": cmd_blast,
        "verdict": cmd_verdict,
        "timeline": cmd_timeline,
        "deleted": cmd_deleted,
    }[args.command](args)


if __name__ == "__main__":
    main()