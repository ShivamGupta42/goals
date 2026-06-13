from __future__ import annotations

from html import escape
from pathlib import Path

from goals.architecture import architecture_for_snapshot, architecture_status_counts, render_mermaid
from goals.decisions import (
    build_decision_context,
    render_decision_explanation,
    should_surface_decision,
)
from goals.ecosystem import recommend_ecosystem_tools
from goals.git_ops import source_commit
from goals.issues import analyze_goal_issues
from goals.memory import derive_memory_suggestions, load_memory
from goals.models import GoalArchitectureMap, GoalSnapshot
from goals.sources import unresolved_claims
from goals.storage import atomic_write_text


def render_dashboard(
    snapshot: GoalSnapshot,
    output_path: Path,
    *,
    architecture: GoalArchitectureMap | None = None,
    architecture_path: Path | None = None,
) -> None:
    status = escape(snapshot.status)
    current = escape(snapshot.current_phase or "none")
    architecture = architecture or architecture_for_snapshot(snapshot)
    surfaced_decisions = [d for d in snapshot.decisions if should_surface_decision(d)[0]]
    issue_report = analyze_goal_issues(snapshot)
    waiting_on = _waiting_on(snapshot, surfaced_decisions, issue_report.user_questions)
    accepted_count = len([p for p in snapshot.phases if p.status == "accepted"])
    total_count = len(snapshot.phases)
    proof_count = len([p for p in snapshot.phases if p.evidence is not None])
    phase_rows = "\n".join(
        f'<tr><td><span class="pill">{escape(p.phase_id)}</span></td>'
        f"<td><strong>{escape(p.title)}</strong><br><span>{escape(p.goal)}</span></td>"
        f"<td>{_status_label(str(p.status))}</td>"
        f"<td>{_evidence_summary(p.evidence.notes if p.evidence else '')}</td></tr>"
        for p in snapshot.phases
    )
    decisions = _decision_html(snapshot, surfaced_decisions)
    issues = _issues_html(issue_report)
    recommendations = _recommendations_html(snapshot)
    memory = _memory_html(snapshot)
    sources = _sources_html(snapshot)
    evidence = "\n".join(
        f"<li>{escape(p.phase_id)}: {escape((p.evidence.notes if p.evidence else 'No evidence yet'))}</li>"
        for p in snapshot.phases
    )
    architecture_html = _architecture_html(architecture, architecture_path)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Goals Dashboard - {escape(snapshot.goal_id)}</title>
  <style>
    :root {{ color-scheme: light; --ink: #172033; --muted: #5f6b7a; --line: #d8dee8; --soft: #f6f7f9; --green: #0f766e; --amber: #a16207; --red: #b42318; --blue: #1d4ed8; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; line-height: 1.45; color: var(--ink); background: #ffffff; }}
    header, section, nav {{ max-width: 1080px; margin: 0 auto; padding: 1.25rem; }}
    header {{ padding-top: 2rem; }}
    h1 {{ font-size: clamp(1.7rem, 3vw, 2.6rem); line-height: 1.1; margin: 0 0 .6rem; letter-spacing: 0; }}
    h2 {{ font-size: 1.2rem; margin: 0 0 .8rem; letter-spacing: 0; }}
    h3 {{ font-size: 1rem; margin: 0 0 .35rem; letter-spacing: 0; }}
    p {{ margin: .25rem 0 .75rem; }}
    nav {{ display: flex; gap: .5rem; flex-wrap: wrap; padding-top: 0; }}
    nav a {{ border: 1px solid var(--line); border-radius: 8px; color: var(--ink); padding: .35rem .65rem; text-decoration: none; background: #fff; }}
    .status {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .75rem; margin-top: 1rem; }}
    .tile {{ border: 1px solid var(--line); border-radius: 8px; padding: .9rem; background: var(--soft); min-height: 5.25rem; }}
    .tile strong {{ display: block; color: var(--muted); font-size: .78rem; text-transform: uppercase; }}
    .tile span {{ display: block; font-size: 1.05rem; margin-top: .25rem; }}
    .plain {{ color: var(--muted); max-width: 760px; }}
    .panel {{ border-top: 1px solid var(--line); }}
    .decision {{ border: 1px solid var(--line); border-radius: 8px; padding: .9rem; margin-bottom: .75rem; }}
    .decision .ask {{ color: var(--red); font-weight: 700; }}
    .architecture-grid {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); gap: 1rem; }}
    .node-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .75rem; list-style: none; padding: 0; }}
    .node-list li {{ border: 1px solid var(--line); border-radius: 8px; padding: .75rem; }}
    .diagram {{ overflow: auto; border: 1px solid var(--line); border-radius: 8px; padding: .75rem; background: #fbfcfe; }}
    .pill, .status-label {{ display: inline-block; border-radius: 999px; padding: .14rem .45rem; font-size: .78rem; border: 1px solid var(--line); background: #fff; }}
    .built {{ color: var(--green); }}
    .blocked {{ color: var(--red); }}
    .in-progress {{ color: var(--blue); }}
    .planned {{ color: var(--amber); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid var(--line); text-align: left; padding: .65rem; vertical-align: top; }}
    code {{ background: #eef2ff; padding: .1rem .25rem; border-radius: 4px; }}
    ul {{ padding-left: 1.15rem; }}
    @media (max-width: 760px) {{ .architecture-grid {{ grid-template-columns: 1fr; }} table, thead, tbody, tr, th, td {{ display: block; }} th {{ display: none; }} td {{ border-bottom: 0; padding: .35rem 0; }} tr {{ border-bottom: 1px solid var(--line); padding: .6rem 0; display: block; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(snapshot.objective)}</h1>
    <p class="plain">{escape(snapshot.why)}</p>
    <div class="status">
      <div class="tile"><strong>Status</strong><span>{status}</span></div>
      <div class="tile"><strong>Current step</strong><span>{current}</span></div>
      <div class="tile"><strong>Waiting on</strong><span>{escape(waiting_on)}</span></div>
      <div class="tile"><strong>Proof recorded</strong><span>{proof_count}/{total_count} phases</span></div>
      <div class="tile"><strong>Progress</strong><span>{accepted_count}/{total_count} accepted</span></div>
      <div class="tile"><strong>Last updated</strong><span>{escape(snapshot.last_updated)}</span></div>
    </div>
  </header>
  <nav aria-label="Dashboard views">
    <a href="#progress">Progress</a>
    <a href="#issues">Issues</a>
    <a href="#decisions">Decisions</a>
    <a href="#ecosystem">Skills & Plugins</a>
    <a href="#memory">Memory</a>
    <a href="#architecture">Architecture</a>
    <a href="#evidence">Evidence</a>
    <a href="#sources">Sources</a>
    <a href="#technical">Technical Details</a>
  </nav>
  <section id="progress" class="panel">
    <h2>Progress</h2>
    <table><thead><tr><th>ID</th><th>Step</th><th>Status</th><th>Plain goal</th></tr></thead><tbody>{phase_rows}</tbody></table>
  </section>
  <section id="issues" class="panel">
    <h2>Issues</h2>
    {issues}
  </section>
  <section id="decisions" class="panel">
    <h2>Decisions Needed</h2>
    {decisions}
  </section>
  <section id="ecosystem" class="panel">
    <h2>Suggested Skills and Plugins</h2>
    {recommendations}
  </section>
  <section id="memory" class="panel">
    <h2>Self-Evolution Memory</h2>
    {memory}
  </section>
  <section id="architecture" class="panel">
    <h2>Architecture Map</h2>
    {architecture_html}
  </section>
  <section id="evidence" class="panel">
    <h2>Proof and Evidence</h2>
    <ul>{evidence}</ul>
  </section>
  <section id="sources" class="panel">
    <h2>Sources</h2>
    {sources}
  </section>
  <section id="technical" class="panel">
    <h2>Technical Details</h2>
    <p>Goal ID: <code>{escape(snapshot.goal_id)}</code></p>
    <p>Event offset: <code>{snapshot.event_count}</code></p>
    <p>Source commit: <code>{escape(source_commit(Path(snapshot.topology.worktree_path)))}</code></p>
    <p>Generated by Goals from sanitized snapshot state. This page is read-only.</p>
  </section>
</body>
</html>
"""
    atomic_write_text(output_path, html)


def _waiting_on(snapshot: GoalSnapshot, surfaced_decisions: list, user_questions: list[str]) -> str:
    if surfaced_decisions or user_questions:
        return "you"
    if snapshot.blockers or snapshot.status == "blocked":
        return "agent to resolve blocker"
    if snapshot.status == "complete":
        return "no one"
    return "agent"


def _issues_html(report) -> str:
    if not report.issues:
        return "<p>No goal issues found.</p>"
    items = "\n".join(
        "<li>"
        f"<strong>{escape(issue.summary)}</strong>"
        f'<p><span class="status-label {escape(issue.severity)}">{escape(issue.severity.upper())}</span> '
        f'<span class="pill">{escape(issue.area)}</span>'
        + (' <span class="pill">needs user</span>' if issue.needs_user else "")
        + "</p>"
        + (f"<p>{escape(issue.detail)}</p>" if issue.detail else "")
        + (
            f"<p><strong>Next:</strong> {escape(issue.suggested_action)}</p>"
            if issue.suggested_action
            else ""
        )
        + "</li>"
        for issue in report.issues[:8]
    )
    return f"<p>{escape(report.summary)}</p><ul>{items}</ul>"


def _status_label(status: str) -> str:
    css = status.replace("_", "-")
    return f'<span class="status-label {escape(css)}">{escape(status)}</span>'


def _evidence_summary(notes: str) -> str:
    return escape(notes or "No evidence yet")


def _decision_html(snapshot: GoalSnapshot, surfaced_decisions: list) -> str:
    if not surfaced_decisions:
        if snapshot.decisions:
            return (
                "<p>No important decisions are waiting on you. "
                "The agent can continue with recorded assumptions.</p>"
            )
        return "<p>No decisions are waiting on you.</p>"
    context = build_decision_context(snapshot)
    items = []
    for decision in surfaced_decisions:
        explanation = render_decision_explanation(decision, context, level="basic")
        first_lines = [line for line in explanation.markdown.splitlines() if line.strip()]
        summary = escape(decision.plain_summary)
        ask = escape(explanation.reason_for_surface)
        reply = escape(decision.suggested_reply or f"I choose: {decision.recommendation}")
        items.append(
            '<article class="decision">'
            f"<h3>{escape(decision.title)}</h3>"
            f"<p>{summary}</p>"
            f'<p class="ask">Why ask: {ask}</p>'
            f"<p><strong>Recommendation:</strong> {escape(decision.recommendation)}</p>"
            f"<p><strong>Suggested reply:</strong> <code>{reply}</code></p>"
            f"<details><summary>Plain explanation</summary><pre>{escape(chr(10).join(first_lines))}</pre></details>"
            "</article>"
        )
    return "\n".join(items)


def _recommendations_html(snapshot: GoalSnapshot) -> str:
    recommendations = recommend_ecosystem_tools(Path(snapshot.topology.worktree_path), snapshot)
    if not recommendations:
        return "<p>No skill or plugin recommendations matched this phase.</p>"
    items = "\n".join(
        "<li>"
        f"<strong>{escape(rec.label)}</strong> "
        f'<span class="pill">{escape(rec.kind)}</span>'
        f"<p>{escape(rec.reason)}</p>"
        + (f"<p><code>{escape(rec.command_hint)}</code></p>" if rec.command_hint else "")
        + ("<p>User approval needed before using this.</p>" if rec.user_approval_required else "")
        + "</li>"
        for rec in recommendations
    )
    return f'<ul class="node-list">{items}</ul>'


def _memory_html(snapshot: GoalSnapshot) -> str:
    suggestions = derive_memory_suggestions(
        load_memory(Path(snapshot.topology.worktree_path), snapshot)
    )
    visible = [suggestion for suggestion in suggestions if suggestion.user_visible]
    if not visible:
        return "<p>No repeated self-evolution friction recorded.</p>"
    items = "\n".join(
        "<li>"
        f"<strong>{escape(suggestion.title)}</strong>"
        f"<p>{escape(suggestion.plain_summary)}</p>"
        f"<p><strong>Recommended change:</strong> {escape(suggestion.recommended_change)}</p>"
        f'<span class="status-label {escape(suggestion.severity)}">{escape(suggestion.severity)}</span>'
        + (
            f"<p><code>{escape(suggestion.suggested_command)}</code></p>"
            if suggestion.suggested_command
            else ""
        )
        + "</li>"
        for suggestion in visible[:6]
    )
    return f'<ul class="node-list">{items}</ul>'


def _sources_html(snapshot: GoalSnapshot) -> str:
    if not snapshot.sources:
        return "<p>No sources recorded yet.</p>"
    source_items = "\n".join(
        "<li>"
        f"<strong>{escape(source.title)}</strong>"
        f"<p>{escape(source.summary or source.locator or 'No summary recorded.')}</p>"
        f'<span class="pill">{escape(source.source_type)}</span> '
        f'<span class="status-label {escape(source.credibility)}">{escape(source.credibility)}</span>'
        "</li>"
        for source in snapshot.sources
    )
    claim_items = "\n".join(
        "<li>"
        f"<strong>{escape(claim.claim)}</strong>"
        f"<p>Sources: {escape(', '.join(claim.source_ids) or 'none')}</p>"
        f"<p>Confidence: {claim.confidence:.0%}</p>"
        "</li>"
        for claim in snapshot.source_claims
    )
    unresolved = unresolved_claims(snapshot)
    warning = (
        f"<p>{len(unresolved)} claim(s) need source cleanup.</p>"
        if unresolved
        else "<p>All recorded claims reference known sources.</p>"
    )
    return (
        f'{warning}<h3>Recorded Sources</h3><ul class="node-list">{source_items}</ul>'
        f"<h3>Source-backed Claims</h3><ul>{claim_items or '<li>No claims recorded yet.</li>'}</ul>"
    )


def _architecture_html(architecture: GoalArchitectureMap, architecture_path: Path | None) -> str:
    counts = architecture_status_counts(architecture)
    count_text = (
        ", ".join(f"{escape(status)}: {count}" for status, count in sorted(counts.items()))
        or "No nodes recorded"
    )
    link = (
        f"<p>Markdown map: <code>{escape(architecture_path.name)}</code></p>"
        if architecture_path
        else ""
    )
    nodes = "\n".join(
        "<li>"
        f"<strong>{escape(node.label)}</strong>"
        f"<p>{escape(node.plain_summary)}</p>"
        f'<span class="status-label {escape(node.status.replace("_", "-"))}">{escape(node.status)}</span>'
        "</li>"
        for node in architecture.nodes
    )
    return f"""
    <p class="plain">{escape(architecture.overview)}</p>
    <p><strong>Status counts:</strong> {count_text}</p>
    {link}
    <div class="architecture-grid">
      <ul class="node-list">{nodes}</ul>
      <pre class="diagram">{escape(render_mermaid(architecture))}</pre>
    </div>
    """
