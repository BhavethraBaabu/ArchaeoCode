"""Transitive dependency traversal and unified dead-file verdict.

Combines staleness (Day 2) + orphan signal (Day 3) into one
scored, ranked output. Also makes blast radius transitive via BFS.
"""
from dataclasses import dataclass, field
from archaeocode.dependencies import DependencyGraphBuilder, FileDependencies
from archaeocode.ownership import OwnershipAnalyzer, FileOwnership


@dataclass
class DeadFileVerdict:
    file_path: str
    staleness_score: float
    is_orphan: bool
    blast_radius: int
    created_by: str
    last_touched_by: str
    days_since_last_touch: int
    original_author_gone: bool
    verdict: str        # DEAD / LIKELY_DEAD / WATCH / ACTIVE
    confidence: float


@dataclass
class BlastRadiusReport:
    file_path: str
    direct_dependents: list[str] = field(default_factory=list)
    transitive_dependents: list[str] = field(default_factory=list)

    @property
    def total_affected(self) -> int:
        return len(set(self.direct_dependents + self.transitive_dependents))


class TransitiveDependencyGraph:
    def __init__(self, graph: dict[str, FileDependencies]):
        self._graph = graph

    def transitive_blast_radius(self, file_path: str) -> BlastRadiusReport:
        """BFS upward through imported_by edges to find all transitively
        affected files if file_path were deleted."""
        report = BlastRadiusReport(file_path=file_path)
        node = self._graph.get(file_path)
        if not node:
            return report

        # deduplicate direct dependents
        report.direct_dependents = list(set(node.imported_by))

        # BFS for transitive
        visited = set(node.imported_by)
        queue = list(set(node.imported_by))

        while queue:
            current = queue.pop(0)
            current_node = self._graph.get(current)
            if not current_node:
                continue
            for parent in current_node.imported_by:
                if parent not in visited:
                    visited.add(parent)
                    queue.append(parent)
                    report.transitive_dependents.append(parent)

        return report


class DeadFileAnalyzer:
    """Combines ownership (Day 2) + dependency graph (Day 3) into verdicts."""

    def __init__(
        self,
        ownership_analyzer: OwnershipAnalyzer,
        dep_graph: TransitiveDependencyGraph,
        all_graph: dict[str, FileDependencies],
    ):
        self._ownership = ownership_analyzer
        self._dep_graph = dep_graph
        self._all_graph = all_graph

    def analyze(self, file_path: str) -> DeadFileVerdict | None:
        ownership: FileOwnership = self._ownership.analyze_file(file_path)
        if not ownership:
            return None

        blast = self._dep_graph.transitive_blast_radius(file_path)
        is_orphan = len(blast.direct_dependents) == 0

        confidence = self._compute_confidence(
            staleness=ownership.staleness_score,
            is_orphan=is_orphan,
            blast_radius=blast.total_affected,
            author_gone=not ownership.original_author_still_active,
        )

        return DeadFileVerdict(
            file_path=file_path,
            staleness_score=ownership.staleness_score,
            is_orphan=is_orphan,
            blast_radius=blast.total_affected,
            created_by=ownership.created_by,
            last_touched_by=ownership.last_touched_by,
            days_since_last_touch=ownership.days_since_last_touch,
            original_author_gone=not ownership.original_author_still_active,
            verdict=self._verdict(confidence, ownership.is_deleted),
            confidence=confidence,
        )

    def analyze_all(self) -> list[DeadFileVerdict]:
        results = []
        for file_path in self._all_graph:
            v = self.analyze(file_path)
            if v:
                results.append(v)
        return sorted(results, key=lambda x: x.confidence, reverse=True)

    def get_dead(self) -> list[DeadFileVerdict]:
        return [v for v in self.analyze_all() if v.verdict in ("DEAD", "LIKELY_DEAD")]

    @staticmethod
    def _compute_confidence(
        staleness: float,
        is_orphan: bool,
        blast_radius: int,
        author_gone: bool,
    ) -> float:
        """
        staleness     40% — how long since last touch
        orphan        35% — nothing imports it
        author gone   15% — original context lost
        blast radius  -10% softener — high dependents = less likely truly dead
        """
        score = 0.0
        score += staleness * 0.40
        score += (1.0 if is_orphan else 0.0) * 0.35
        score += (1.0 if author_gone else 0.0) * 0.15
        if blast_radius > 5:
            score -= 0.10
        elif blast_radius > 0:
            score -= 0.05
        return round(max(0.0, min(score, 1.0)), 3)

    @staticmethod
    def _verdict(confidence: float, is_deleted: bool) -> str:
        if is_deleted:
            return "DELETED"
        if confidence >= 0.70:
            return "DEAD"
        if confidence >= 0.45:
            return "LIKELY_DEAD"
        if confidence >= 0.25:
            return "WATCH"
        return "ACTIVE"