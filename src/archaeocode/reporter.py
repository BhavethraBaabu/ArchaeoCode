"""HTML report generator — packages all archaeology findings into a
single shareable HTML file an engineering manager can open in a browser."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from archaeocode.ownership import OwnershipAnalyzer
from archaeocode.dependencies import DependencyGraphBuilder
from archaeocode.graph import TransitiveDependencyGraph, DeadFileAnalyzer
from archaeocode.timeline import TimelineAnalyzer
from archaeocode.nlp import CommitNLPAnalyzer
from archaeocode.models import get_engine, get_session


def generate_report_html(repo_path: str, db_path: str) -> str:
    engine = get_engine(db_path)
    session = get_session(engine)

    ownership_analyzer = OwnershipAnalyzer(session)
    nlp_analyzer = CommitNLPAnalyzer(session)
    timeline_analyzer = TimelineAnalyzer(session)
    builder = DependencyGraphBuilder(repo_path)
    graph = builder.build()
    tdg = TransitiveDependencyGraph(graph)
    dead_analyzer = DeadFileAnalyzer(ownership_analyzer, tdg, graph)

    dead_files = dead_analyzer.get_dead()
    timeline = timeline_analyzer.build_monthly_timeline()
    deleted = timeline_analyzer.find_deleted_features(min_lifetime_days=30)
    intent_summary = nlp_analyzer.get_repo_intent_summary()
    bug_prone = nlp_analyzer.get_most_bug_prone_files(top=10)

    html = _render_html(
        repo_path=repo_path,
        dead_files=dead_files,
        timeline=timeline,
        deleted=deleted,
        intent_summary=intent_summary,
        bug_prone=bug_prone,
        graph=graph,
        tdg=tdg,
    )
    session.close()
    return html


def generate_report(repo_path: str, db_path: str, output_path: str = "archaeocode_report.html"):
    html = generate_report_html(repo_path, db_path)
    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


def _render_html(repo_path, dead_files, timeline, deleted, intent_summary, bug_prone, graph, tdg):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # dead files rows
    dead_rows = ""
    for v in dead_files[:30]:
        verdict_color = "#e74c3c" if v.verdict == "DEAD" else "#f39c12"
        dead_rows += f"""
        <tr>
            <td><span class="badge" style="background:{verdict_color}">{v.verdict}</span></td>
            <td class="conf">{v.confidence:.2f}</td>
            <td class="filepath">{v.file_path}</td>
            <td>{v.days_since_last_touch}</td>
            <td>{"✓" if v.is_orphan else ""}</td>
            <td>{"✓" if v.original_author_gone else ""}</td>
            <td>{v.created_by}</td>
        </tr>"""

    # timeline rows
    timeline_rows = ""
    timeline_chart_labels = []
    timeline_chart_data = []
    for s in timeline[-24:]:
        net_color = "#27ae60" if s.net_change >= 0 else "#e74c3c"
        net_sign = "+" if s.net_change >= 0 else ""
        timeline_rows += f"""
        <tr>
            <td>{s.year_month}</td>
            <td>{s.commit_count}</td>
            <td class="green">{s.files_added}</td>
            <td class="red">{s.files_deleted}</td>
            <td>{s.files_modified}</td>
            <td style="color:{net_color};font-weight:bold">{net_sign}{s.net_change}</td>
            <td>{s.top_author[:25]}</td>
        </tr>"""
        timeline_chart_labels.append(f'"{s.year_month}"')
        timeline_chart_data.append(s.commit_count)

    # deleted features rows
    deleted_rows = ""
    for f in deleted[:20]:
        deleted_rows += f"""
        <tr>
            <td class="filepath">{f.file_path}</td>
            <td>{f.module}</td>
            <td>{f.lifetime_days}</td>
            <td>{f.created_by[:20]}</td>
            <td>{f.deleted_by[:20]}</td>
            <td>{f.created_at.strftime("%Y-%m-%d")}</td>
            <td>{f.deleted_at.strftime("%Y-%m-%d")}</td>
        </tr>"""

    # intent chart data
    intent_colors = {
        "feature": "#27ae60", "bugfix": "#e74c3c", "refactor": "#3498db",
        "deprecation": "#9b59b6", "docs": "#1abc9c", "test": "#f39c12",
        "chore": "#95a1a8", "security": "#c0392b", "performance": "#2ecc71",
    }
    intent_labels = [f'"{k}"' for k in intent_summary.keys()]
    intent_values = list(intent_summary.values())
    intent_bg = [f'"{intent_colors.get(k, "#95a1a8")}"' for k in intent_summary.keys()]

    # bug prone rows
    bug_rows = ""
    for path, count in bug_prone:
        if count > 0:
            bug_rows += f"""
            <tr>
                <td class="filepath">{path}</td>
                <td><span class="badge" style="background:#e74c3c">{count} bugfix commits</span></td>
            </tr>"""

    # stats for hero section
    total_files = len(graph)
    dead_count = len([v for v in dead_files if v.verdict == "DEAD"])
    likely_dead_count = len([v for v in dead_files if v.verdict == "LIKELY_DEAD"])
    deleted_count = len(deleted)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ArchaeoCode Report — {repo_path}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0d1117; color: #c9d1d9; line-height: 1.6; }}
  a {{ color: #58a6ff; }}
  header {{ background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
            border-bottom: 1px solid #30363d; padding: 2rem 3rem; }}
  header h1 {{ font-size: 1.8rem; color: #f0f6fc; }}
  header h1 span {{ color: #58a6ff; }}
  header p {{ color: #8b949e; margin-top: 0.3rem; font-size: 0.9rem; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem 3rem; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr);
                 gap: 1rem; margin: 2rem 0; }}
  .stat-card {{ background: #161b22; border: 1px solid #30363d;
                border-radius: 8px; padding: 1.5rem; text-align: center; }}
  .stat-card .number {{ font-size: 2.5rem; font-weight: 700; color: #f0f6fc; }}
  .stat-card .label {{ color: #8b949e; font-size: 0.85rem; margin-top: 0.3rem; }}
  .stat-card.red .number {{ color: #e74c3c; }}
  .stat-card.yellow .number {{ color: #f39c12; }}
  .stat-card.blue .number {{ color: #58a6ff; }}
  .stat-card.green .number {{ color: #27ae60; }}
  section {{ margin: 3rem 0; }}
  section h2 {{ font-size: 1.3rem; color: #f0f6fc; border-bottom: 1px solid #30363d;
                padding-bottom: 0.75rem; margin-bottom: 1.5rem; }}
  section h2 .count {{ color: #8b949e; font-size: 1rem; font-weight: normal;
                       margin-left: 0.5rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ background: #161b22; color: #8b949e; text-align: left; padding: 0.75rem 1rem;
        border-bottom: 1px solid #30363d; font-weight: 600;
        text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }}
  td {{ padding: 0.65rem 1rem; border-bottom: 1px solid #21262d; vertical-align: middle; }}
  tr:hover td {{ background: #161b22; }}
  .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px;
             font-size: 0.75rem; font-weight: 700; color: white; }}
  .filepath {{ font-family: "SF Mono", monospace; font-size: 0.8rem; color: #79c0ff; }}
  .conf {{ font-weight: 700; color: #f0f6fc; }}
  .green {{ color: #27ae60; }}
  .red {{ color: #e74c3c; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin: 1.5rem 0; }}
  .chart-box {{ background: #161b22; border: 1px solid #30363d;
                border-radius: 8px; padding: 1.5rem; }}
  .chart-box h3 {{ color: #8b949e; font-size: 0.85rem; margin-bottom: 1rem;
                   text-transform: uppercase; letter-spacing: 0.05em; }}
  footer {{ text-align: center; padding: 2rem; color: #8b949e;
             font-size: 0.8rem; border-top: 1px solid #30363d; margin-top: 3rem; }}
  .empty {{ color: #8b949e; font-style: italic; padding: 1rem; }}
</style>
</head>
<body>

<header>
  <h1>⛏ <span>ArchaeoCode</span> Report</h1>
  <p>Repo: <strong>{repo_path}</strong> &nbsp;·&nbsp; Generated: {generated_at}</p>
</header>

<div class="container">

  <div class="stats-grid">
    <div class="stat-card blue">
      <div class="number">{total_files}</div>
      <div class="label">Python files analyzed</div>
    </div>
    <div class="stat-card red">
      <div class="number">{dead_count}</div>
      <div class="label">Dead files</div>
    </div>
    <div class="stat-card yellow">
      <div class="number">{likely_dead_count}</div>
      <div class="label">Likely dead files</div>
    </div>
    <div class="stat-card green">
      <div class="number">{deleted_count}</div>
      <div class="label">Deleted features found</div>
    </div>
  </div>

  <!-- Charts -->
  <div class="chart-grid">
    <div class="chart-box">
      <h3>Commit Activity (last 24 months)</h3>
      <canvas id="timelineChart" height="200"></canvas>
    </div>
    <div class="chart-box">
      <h3>Commit Intent Distribution</h3>
      <canvas id="intentChart" height="200"></canvas>
    </div>
  </div>

  <!-- Dead File Verdicts -->
  <section>
    <h2>Dead File Verdicts <span class="count">({len(dead_files)} files flagged)</span></h2>
    <table>
      <thead>
        <tr>
          <th>Verdict</th><th>Confidence</th><th>File</th>
          <th>Days Idle</th><th>Orphan</th><th>Author Gone</th><th>Created By</th>
        </tr>
      </thead>
      <tbody>
        {dead_rows if dead_rows else '<tr><td colspan="7" class="empty">No dead files detected</td></tr>'}
      </tbody>
    </table>
  </section>

  <!-- Architecture Timeline -->
  <section>
    <h2>Architecture Timeline <span class="count">(monthly)</span></h2>
    <table>
      <thead>
        <tr>
          <th>Month</th><th>Commits</th><th>Added</th>
          <th>Deleted</th><th>Modified</th><th>Net</th><th>Top Author</th>
        </tr>
      </thead>
      <tbody>{timeline_rows}</tbody>
    </table>
  </section>

  <!-- Deleted Features -->
  <section>
    <h2>Deleted Features <span class="count">({len(deleted)} found, lived &gt;30 days)</span></h2>
    <table>
      <thead>
        <tr>
          <th>File</th><th>Module</th><th>Lifetime (days)</th>
          <th>Created By</th><th>Deleted By</th><th>Created At</th><th>Deleted At</th>
        </tr>
      </thead>
      <tbody>
        {deleted_rows if deleted_rows else '<tr><td colspan="7" class="empty">No deleted features found</td></tr>'}
      </tbody>
    </table>
  </section>

  <!-- Most Bug-Prone Files -->
  <section>
    <h2>Most Bug-Prone Files</h2>
    <table>
      <thead><tr><th>File</th><th>Bugfix Commits</th></tr></thead>
      <tbody>
        {bug_rows if bug_rows else '<tr><td colspan="2" class="empty">No bugfix commits detected</td></tr>'}
      </tbody>
    </table>
  </section>

</div>

<footer>
  Generated by <strong>ArchaeoCode</strong> — AI-powered codebase archaeology
</footer>

<script>
  // Timeline chart
  new Chart(document.getElementById("timelineChart"), {{
    type: "bar",
    data: {{
      labels: [{",".join(timeline_chart_labels)}],
      datasets: [{{
        label: "Commits",
        data: [{",".join(str(x) for x in timeline_chart_data)}],
        backgroundColor: "#58a6ff44",
        borderColor: "#58a6ff",
        borderWidth: 1,
        borderRadius: 3,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: "#8b949e", maxRotation: 45 }}, grid: {{ color: "#21262d" }} }},
        y: {{ ticks: {{ color: "#8b949e" }}, grid: {{ color: "#21262d" }} }}
      }}
    }}
  }});

  // Intent donut chart
  new Chart(document.getElementById("intentChart"), {{
    type: "doughnut",
    data: {{
      labels: [{",".join(intent_labels)}],
      datasets: [{{
        data: [{",".join(str(x) for x in intent_values)}],
        backgroundColor: [{",".join(intent_bg)}],
        borderWidth: 0,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{
          position: "right",
          labels: {{ color: "#8b949e", font: {{ size: 11 }} }}
        }}
      }}
    }}
  }});
</script>
</body>
</html>"""