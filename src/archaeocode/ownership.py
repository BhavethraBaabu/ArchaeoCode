"""Ownership evolution and dead-file detection.

For each file ever touched in the repo, reconstructs:
- who created it
- who owns it now (most recent + most frequent author)
- how long it's been since the last touch (staleness)
- whether the original author still appears active in the repo
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from archaeocode.models import Commit, FileChange


@dataclass
class FileOwnership:
    file_path: str
    created_by: str
    created_at: datetime
    current_owner: str          # most frequent recent committer
    last_touched_by: str
    last_touched_at: datetime
    total_commits: int
    days_since_last_touch: int
    original_author_still_active: bool
    staleness_score: float       # 0.0 (fresh) -> 1.0 (likely dead)
    is_deleted: bool


class OwnershipAnalyzer:
    def __init__(self, session: Session):
        self.session = session
        self._repo_last_activity = self._get_repo_last_activity()
        self._active_authors = self._get_active_authors()

    def _get_repo_last_activity(self) -> datetime:
        latest = self.session.query(func.max(Commit.committed_date)).scalar()
        return latest or datetime.now()

    def _get_active_authors(self, recent_commit_window: int = 50) -> set:
        """Authors who appear in the most recent N commits — proxy for
        'still working on this repo'."""
        recent = (
            self.session.query(Commit.author_email)
            .order_by(Commit.committed_date.desc())
            .limit(recent_commit_window)
            .all()
        )
        return {r[0] for r in recent}

    def analyze_file(self, file_path: str) -> Optional[FileOwnership]:
        changes = (
            self.session.query(FileChange, Commit)
            .join(Commit, FileChange.commit_id == Commit.id)
            .filter(FileChange.file_path == file_path)
            .order_by(Commit.committed_date.asc())
            .all()
        )
        if not changes:
            return None

        first_change, first_commit = changes[0]
        last_change, last_commit = changes[-1]

        # current owner = most frequent author among this file's commits
        author_counts: dict[str, int] = {}
        for _, commit in changes:
            author_counts[commit.author_name] = author_counts.get(commit.author_name, 0) + 1
        current_owner = max(author_counts, key=author_counts.get)

        days_since = (self._repo_last_activity - last_commit.committed_date).days
        is_deleted = last_change.change_type == "D"

        # is the file's original author still showing up in recent commits?
        original_active = self._is_author_active(first_commit.author_email)

        staleness = self._compute_staleness(days_since, len(changes), is_deleted)

        return FileOwnership(
            file_path=file_path,
            created_by=first_commit.author_name,
            created_at=first_commit.committed_date,
            current_owner=current_owner,
            last_touched_by=last_commit.author_name,
            last_touched_at=last_commit.committed_date,
            total_commits=len(changes),
            days_since_last_touch=days_since,
            original_author_still_active=original_active,
            staleness_score=staleness,
            is_deleted=is_deleted,
        )

    def _is_author_active(self, author_email: str) -> bool:
        return author_email in self._active_authors

    @staticmethod
    def _compute_staleness(days_since: int, total_commits: int, is_deleted: bool) -> float:
        """Simple heuristic for v1 — gets replaced by a smarter model later.

        - deleted files are maximally stale (score 1.0)
        - more days untouched -> higher staleness
        - more historical commits (well-maintained once) softens the score slightly,
          since heavily-iterated files are less likely to be truly abandoned
        """
        if is_deleted:
            return 1.0

        # normalize days_since against a 2-year horizon
        time_factor = min(days_since / 730, 1.0)
        churn_softener = min(total_commits / 20, 1.0) * 0.15

        score = max(0.0, time_factor - churn_softener)
        return round(score, 3)

    def analyze_all_files(self) -> list[FileOwnership]:
        file_paths = (
            self.session.query(FileChange.file_path)
            .distinct()
            .all()
        )
        results = []
        for (path,) in file_paths:
            result = self.analyze_file(path)
            if result:
                results.append(result)
        return results

    def get_dead_file_candidates(self, threshold: float = 0.6) -> list[FileOwnership]:
        """Files most likely to be dead/abandoned, sorted worst-first."""
        all_files = self.analyze_all_files()
        dead = [f for f in all_files if f.staleness_score >= threshold and not f.is_deleted]
        return sorted(dead, key=lambda f: f.staleness_score, reverse=True)

    def get_orphaned_files(self) -> list[FileOwnership]:
        """Files whose original author is gone AND current owner is also gone —
        classic 'nobody understands this' signal."""
        all_files = self.analyze_all_files()
        orphaned = [
            f for f in all_files
            if not f.original_author_still_active and f.staleness_score >= 0.4
        ]
        return sorted(orphaned, key=lambda f: f.staleness_score, reverse=True)