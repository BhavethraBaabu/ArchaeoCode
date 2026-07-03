"""Commit message NLP — extract intent and categorize why files changed.

Day 6: no external API needed. Uses keyword classification + regex
pattern matching to extract intent from commit messages and build a
"why did this file change?" history for any file in the repo.
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

from archaeocode.models import Commit, FileChange


# Intent categories with weighted keyword signals
INTENT_PATTERNS: dict[str, list[str]] = {
    "feature":     ["add", "implement", "introduce", "support", "new", "create", "build", "enable"],
    "bugfix":      ["fix", "bug", "patch", "resolve", "correct", "repair", "issue", "crash", "error"],
    "refactor":    ["refactor", "restructure", "reorganize", "clean", "simplify", "rename", "move", "extract"],
    "deprecation": ["deprecate", "remove", "delete", "drop", "obsolete", "replace", "retire"],
    "docs":        ["doc", "docs", "documentation", "readme", "comment", "changelog", "example"],
    "test":        ["test", "tests", "testing", "coverage", "spec", "assert", "mock", "fixture"],
    "chore":       ["bump", "upgrade", "update", "dependency", "version", "release", "ci", "lint", "format"],
    "security":    ["security", "cve", "vulnerability", "sanitize", "escape", "auth", "permission"],
    "performance": ["perf", "performance", "optimize", "speed", "cache", "slow", "fast", "memory"],
}

# Regex patterns for extracting structured info from commit messages
TICKET_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d+)\b")             # JIRA-123, GH-456
PR_PATTERN = re.compile(r"#(\d+)")                                  # #123
BREAKING_PATTERN = re.compile(r"breaking.change|BREAKING", re.I)
REVERT_PATTERN = re.compile(r"^revert[\s:]", re.I)
CO_AUTHOR_PATTERN = re.compile(r"Co-authored-by:\s*(.+?)\s*<", re.I)


@dataclass
class CommitIntent:
    sha: str
    message: str
    author: str
    date: datetime
    intent: str              # primary category (feature/bugfix/refactor etc.)
    confidence: float        # 0.0 -> 1.0
    secondary_intents: list[str]
    is_breaking: bool
    is_revert: bool
    referenced_tickets: list[str]
    referenced_prs: list[str]
    co_authors: list[str]
    summary: str             # one-line cleaned summary of the commit


@dataclass
class FileChangeReason:
    file_path: str
    total_changes: int
    intent_breakdown: dict[str, int]     # intent -> count
    dominant_intent: str
    breaking_change_count: int
    revert_count: int
    change_history: list[dict]           # [{date, author, intent, summary}]


class CommitNLPAnalyzer:
    def __init__(self, session: Session):
        self.session = session
        self._intent_cache: dict[str, CommitIntent] = {}

    def classify_commit(self, commit: Commit) -> CommitIntent:
        """Classify a single commit's intent from its message."""
        if commit.sha in self._intent_cache:
            return self._intent_cache[commit.sha]

        message = commit.message or ""
        first_line = message.split("\n")[0].strip()
        lower = message.lower()

        # score each intent category
        scores: dict[str, float] = {}
        for intent, keywords in INTENT_PATTERNS.items():
            score = 0.0
            for kw in keywords:
                # word boundary match weighted higher than substring
                if re.search(rf"\b{re.escape(kw)}\b", lower):
                    score += 1.0
                elif kw in lower:
                    score += 0.4
            scores[intent] = score

        total = sum(scores.values())
        if total == 0:
            primary_intent = "chore"
            confidence = 0.1
            secondary = []
        else:
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            primary_intent = ranked[0][0]
            confidence = min(ranked[0][1] / max(total, 1), 1.0)
            secondary = [i for i, s in ranked[1:] if s > 0][:2]

        result = CommitIntent(
            sha=commit.sha,
            message=message,
            author=commit.author_name,
            date=commit.committed_date,
            intent=primary_intent,
            confidence=round(confidence, 3),
            secondary_intents=secondary,
            is_breaking=bool(BREAKING_PATTERN.search(message)),
            is_revert=bool(REVERT_PATTERN.match(first_line)),
            referenced_tickets=TICKET_PATTERN.findall(message),
            referenced_prs=PR_PATTERN.findall(message),
            co_authors=CO_AUTHOR_PATTERN.findall(message),
            summary=self._clean_summary(first_line),
        )

        self._intent_cache[commit.sha] = result
        return result

    def analyze_file_history(self, file_path: str) -> FileChangeReason | None:
        """For a given file, classify every commit that touched it
        and return a structured reason breakdown."""
        changes = (
            self.session.query(FileChange, Commit)
            .join(Commit, FileChange.commit_id == Commit.id)
            .filter(FileChange.file_path == file_path)
            .order_by(Commit.committed_date.desc())
            .all()
        )
        if not changes:
            return None

        intent_counts: dict[str, int] = defaultdict(int)
        breaking = 0
        reverts = 0
        history = []

        for _, commit in changes:
            classified = self.classify_commit(commit)
            intent_counts[classified.intent] += 1
            if classified.is_breaking:
                breaking += 1
            if classified.is_revert:
                reverts += 1
            history.append({
                "date": classified.date.strftime("%Y-%m-%d"),
                "author": classified.author,
                "intent": classified.intent,
                "summary": classified.summary,
                "is_breaking": classified.is_breaking,
                "tickets": classified.referenced_tickets,
            })

        dominant = max(intent_counts, key=intent_counts.get)

        return FileChangeReason(
            file_path=file_path,
            total_changes=len(changes),
            intent_breakdown=dict(intent_counts),
            dominant_intent=dominant,
            breaking_change_count=breaking,
            revert_count=reverts,
            change_history=history,
        )

    def analyze_all_files(self) -> list[FileChangeReason]:
        """Classify change reasons for every file in the db."""
        file_paths = (
            self.session.query(FileChange.file_path)
            .distinct()
            .all()
        )
        results = []
        for (path,) in file_paths:
            r = self.analyze_file_history(path)
            if r:
                results.append(r)
        return sorted(results, key=lambda x: x.total_changes, reverse=True)

    def get_repo_intent_summary(self) -> dict[str, int]:
        """High-level breakdown of what the repo's commit history is
        mostly about — feature work vs bugfixes vs chores etc."""
        commits = self.session.query(Commit).all()
        summary: dict[str, int] = defaultdict(int)
        for commit in commits:
            classified = self.classify_commit(commit)
            summary[classified.intent] += 1
        return dict(sorted(summary.items(), key=lambda x: x[1], reverse=True))

    def get_most_bug_prone_files(self, top: int = 10) -> list[tuple[str, int]]:
        """Files with the highest number of bugfix commits — useful for
        flagging risky files before deletion."""
        all_files = self.analyze_all_files()
        scored = [
            (f.file_path, f.intent_breakdown.get("bugfix", 0))
            for f in all_files
        ]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:top]

    @staticmethod
    def _clean_summary(first_line: str) -> str:
        """Strip conventional commit prefixes and ticket refs for a
        clean one-line summary."""
        # strip "feat:", "fix(auth):", "chore!:" etc.
        cleaned = re.sub(r"^[a-z]+(\([^)]+\))?!?:\s*", "", first_line, flags=re.I)
        # strip leading ticket refs like "[JIRA-123]"
        cleaned = re.sub(r"^\[[A-Z]+-\d+\]\s*", "", cleaned)
        return cleaned.strip() or first_line