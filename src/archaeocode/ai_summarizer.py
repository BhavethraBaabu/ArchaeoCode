"""AI layer — uses Groq (Llama 3.3) to explain why each module exists."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

from archaeocode.ownership import OwnershipAnalyzer, FileOwnership
from archaeocode.graph import TransitiveDependencyGraph, DeadFileVerdict, DeadFileAnalyzer
from archaeocode.dependencies import FileDependencies
from archaeocode.nlp import CommitNLPAnalyzer, FileChangeReason

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass
class ModuleSummary:
    file_path: str
    one_liner: str
    purpose: str
    risk_assessment: str
    recommendation: str
    key_facts: list[str]


class AISummarizer:
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in .env")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def summarize_file(self, file_path, ownership, change_reason, deps, verdict):
        context = self._build_context(file_path, ownership, change_reason, deps, verdict)
        prompt = self._build_prompt(file_path, context)
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_response(file_path, response.choices[0].message.content)

    def summarize_repo(self, ownership_analyzer, nlp_analyzer, dep_graph, dead_analyzer, top_files=5):
        all_files = list(dep_graph.keys())
        tdg = TransitiveDependencyGraph(dep_graph)
        scored = []
        for path in all_files:
            blast = tdg.transitive_blast_radius(path).total_affected
            change = nlp_analyzer.analyze_file_history(path)
            commits = change.total_changes if change else 0
            scored.append((path, blast * 2 + commits))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = [path for path, _ in scored[:top_files]]
        summaries = []
        verdicts = {v.file_path: v for v in dead_analyzer.analyze_all()}

        for path in top:
            ownership = ownership_analyzer.analyze_file(path)
            change_reason = nlp_analyzer.analyze_file_history(path)
            deps = dep_graph.get(path)
            verdict = verdicts.get(path)
            summary = self.summarize_file(path, ownership, change_reason, deps, verdict)
            summaries.append(summary)

        return summaries

    def _build_context(self, file_path, ownership, change_reason, deps, verdict):
        lines = [f"File: {file_path}"]

        if ownership:
            lines += [
                f"Created by: {ownership.created_by} on {ownership.created_at.strftime('%Y-%m-%d')}",
                f"Current owner (most commits): {ownership.current_owner}",
                f"Last touched: {ownership.days_since_last_touch} days ago by {ownership.last_touched_by}",
                f"Original author still active: {ownership.original_author_still_active}",
                f"Staleness score: {ownership.staleness_score} (0=fresh, 1=dead)",
            ]

        if change_reason:
            lines += [
                f"Total commits touching this file: {change_reason.total_changes}",
                f"Dominant change intent: {change_reason.dominant_intent}",
                f"Intent breakdown: {change_reason.intent_breakdown}",
                f"Breaking changes: {change_reason.breaking_change_count}",
                f"Reverts: {change_reason.revert_count}",
            ]
            recent = change_reason.change_history[:5]
            if recent:
                lines.append("Recent commit summaries:")
                for entry in recent:
                    lines.append(f"  [{entry['date']}] {entry['intent']}: {entry['summary']}")

        if deps:
            lines += [
                f"This file imports: {len(deps.imports)} internal files",
                f"This file is imported by: {len(deps.imported_by)} files",
            ]
            if deps.imported_by:
                lines.append(f"Imported by (sample): {', '.join(deps.imported_by[:5])}")

        if verdict:
            lines += [
                f"Dead-file verdict: {verdict.verdict} (confidence: {verdict.confidence})",
                f"Is orphan (nothing imports it): {verdict.is_orphan}",
                f"Transitive blast radius: {verdict.blast_radius} files affected if deleted",
            ]

        return "\n".join(lines)

    def _build_prompt(self, file_path, context):
        return f"""You are a senior software archaeologist analyzing a codebase for an engineering team.

You have been given structured archaeology data about a file. Your job is to synthesize
this into a clear, actionable summary that a new engineer could read to understand:
- What this file does
- Why it exists
- Whether it's safe to delete or modify
- What an engineering manager should do about it

Archaeology data:
{context}

Respond in exactly this format (keep each section concise):

ONE_LINER: <one sentence: "This file does X">
PURPOSE: <2-3 sentences explaining why this file exists based on its history>
RISK: <one of: CRITICAL / HIGH / MEDIUM / LOW / SAFE_TO_DELETE — with one sentence explaining why>
RECOMMENDATION: <one concrete action an engineering manager should take>
KEY_FACTS:
- <fact 1>
- <fact 2>
- <fact 3>

Be direct and specific. Do not hedge excessively. Base everything on the data provided."""

    def _parse_response(self, file_path, raw):
        lines = raw.strip().split("\n")
        one_liner = ""
        purpose = ""
        risk = ""
        recommendation = ""
        key_facts = []
        in_facts = False

        for line in lines:
            line = line.strip()
            if line.startswith("ONE_LINER:"):
                one_liner = line.replace("ONE_LINER:", "").strip()
            elif line.startswith("PURPOSE:"):
                purpose = line.replace("PURPOSE:", "").strip()
            elif line.startswith("RISK:"):
                risk = line.replace("RISK:", "").strip()
            elif line.startswith("RECOMMENDATION:"):
                recommendation = line.replace("RECOMMENDATION:", "").strip()
            elif line.startswith("KEY_FACTS:"):
                in_facts = True
            elif in_facts and line.startswith("-"):
                key_facts.append(line[1:].strip())

        return ModuleSummary(
            file_path=file_path,
            one_liner=one_liner,
            purpose=purpose,
            risk_assessment=risk,
            recommendation=recommendation,
            key_facts=key_facts,
        )