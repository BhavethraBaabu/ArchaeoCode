"""Extracts commit and file-change history from a git repository."""
from datetime import datetime
from pathlib import Path

import git
from rich.progress import track

from archaeocode.models import Commit, FileChange, get_engine, get_session


class RepoExtractor:
    def __init__(self, repo_path: str, db_path: str = "archaeocode.db"):
        self.repo_path = Path(repo_path).resolve()
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"{self.repo_path} is not a git repository")

        self.repo = git.Repo(self.repo_path)
        self.engine = get_engine(db_path)

    def extract_all(self, branch: str = None, limit: int = None):
        """Walk every commit on the given branch (default: current HEAD)
        and persist commit + file-change records."""
        session = get_session(self.engine)

        commits = list(
            self.repo.iter_commits(branch or self.repo.head.reference, max_count=limit)
        )

        for git_commit in track(commits, description="Excavating commit history..."):
            existing = session.query(Commit).filter_by(sha=git_commit.hexsha).first()
            if existing:
                continue  # already indexed, skip (makes re-runs cheap)

            stats = git_commit.stats
            commit_row = Commit(
                sha=git_commit.hexsha,
                author_name=git_commit.author.name,
                author_email=git_commit.author.email,
                message=git_commit.message.strip(),
                committed_date=datetime.fromtimestamp(git_commit.committed_date),
                insertions=stats.total.get("insertions", 0),
                deletions=stats.total.get("deletions", 0),
                files_changed_count=len(stats.files),
            )
            session.add(commit_row)
            session.flush()  # get commit_row.id without full commit

            for file_path, file_stats in stats.files.items():
                change_type = self._infer_change_type(git_commit, file_path)
                session.add(
                    FileChange(
                        commit_id=commit_row.id,
                        file_path=file_path,
                        change_type=change_type,
                        insertions=file_stats.get("insertions", 0),
                        deletions=file_stats.get("deletions", 0),
                    )
                )

        session.commit()
        session.close()
        return len(commits)

    @staticmethod
    def _infer_change_type(git_commit, file_path: str) -> str:
        """Best-effort change type using the diff against the first parent."""
        if not git_commit.parents:
            return "A"  # initial commit, everything is "added"
        try:
            diffs = git_commit.parents[0].diff(git_commit, paths=file_path)
            if diffs:
                return diffs[0].change_type
        except Exception:
            pass
        return "M"