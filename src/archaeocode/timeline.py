"""Architecture timeline and deleted features detector.

Day 5: answers two questions:
1. How did the codebase grow/shrink month by month?
2. What features (files/modules) used to exist but were deleted?
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

from archaeocode.models import Commit, FileChange


@dataclass
class MonthSnapshot:
    year_month: str          # "2021-03"
    files_added: int
    files_deleted: int
    files_modified: int
    net_change: int          # added - deleted
    cumulative_files: int    # running total of live files
    top_author: str
    commit_count: int


@dataclass
class DeletedFeature:
    file_path: str
    created_at: datetime
    deleted_at: datetime
    lifetime_days: int
    created_by: str
    deleted_by: str
    commit_count: int        # how many times it was touched before deletion
    module: str              # top-level module/folder it belonged to


class TimelineAnalyzer:
    def __init__(self, session: Session):
        self.session = session

    def build_monthly_timeline(self) -> list[MonthSnapshot]:
        """Builds a month-by-month snapshot of codebase growth."""
        changes = (
            self.session.query(FileChange, Commit)
            .join(Commit, FileChange.commit_id == Commit.id)
            .order_by(Commit.committed_date.asc())
            .all()
        )

        # group by year-month
        monthly: dict[str, dict] = defaultdict(lambda: {
            "added": 0, "deleted": 0, "modified": 0,
            "authors": defaultdict(int), "commits": set()
        })

        for change, commit in changes:
            ym = commit.committed_date.strftime("%Y-%m")
            bucket = monthly[ym]
            bucket["commits"].add(commit.sha)
            bucket["authors"][commit.author_name] += 1

            if change.change_type == "A":
                bucket["added"] += 1
            elif change.change_type == "D":
                bucket["deleted"] += 1
            else:
                bucket["modified"] += 1

        # build snapshots with running cumulative count
        snapshots = []
        cumulative = 0
        for ym in sorted(monthly.keys()):
            b = monthly[ym]
            net = b["added"] - b["deleted"]
            cumulative += net
            top_author = max(b["authors"], key=b["authors"].get) if b["authors"] else "unknown"
            snapshots.append(MonthSnapshot(
                year_month=ym,
                files_added=b["added"],
                files_deleted=b["deleted"],
                files_modified=b["modified"],
                net_change=net,
                cumulative_files=max(cumulative, 0),
                top_author=top_author,
                commit_count=len(b["commits"]),
            ))

        return snapshots

    def find_deleted_features(self, min_lifetime_days: int = 30) -> list[DeletedFeature]:
        """Finds files that were created, lived for a while, then deleted.

        min_lifetime_days filters out noise (temp files deleted same week).
        """
        # get full history per file, ordered by date
        file_history: dict[str, list[tuple[FileChange, Commit]]] = defaultdict(list)
        changes = (
            self.session.query(FileChange, Commit)
            .join(Commit, FileChange.commit_id == Commit.id)
            .order_by(Commit.committed_date.asc())
            .all()
        )
        for change, commit in changes:
            file_history[change.file_path].append((change, commit))

        deleted_features = []
        for file_path, history in file_history.items():
            change_types = [c.change_type for c, _ in history]

            # must have been added AND later deleted
            if "A" not in change_types or "D" not in change_types:
                continue

            # find first add and last delete
            first_add = next(
                (commit for change, commit in history if change.change_type == "A"), None
            )
            last_delete = next(
                (commit for change, commit in reversed(history) if change.change_type == "D"), None
            )

            if not first_add or not last_delete:
                continue

            lifetime = (last_delete.committed_date - first_add.committed_date).days
            if lifetime < min_lifetime_days:
                continue

            module = file_path.split("/")[0] if "/" in file_path else "root"

            deleted_features.append(DeletedFeature(
                file_path=file_path,
                created_at=first_add.committed_date,
                deleted_at=last_delete.committed_date,
                lifetime_days=lifetime,
                created_by=first_add.author_name,
                deleted_by=last_delete.author_name,
                commit_count=len(history),
                module=module,
            ))

        return sorted(deleted_features, key=lambda f: f.lifetime_days, reverse=True)