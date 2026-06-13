from __future__ import annotations

from html import escape
from pathlib import Path

from goals.architecture import (
    analyze_code_architecture,
    architecture_for_snapshot,
    architecture_status_counts,
    build_architecture_brief,
    render_mermaid,
)
from goals.assets import analyze_asset_provenance
from goals.brief import build_goal_brief
from goals.citations import analyze_citation_quality
from goals.creative import analyze_creative_variants
from goals.decisions import (
    build_decision_brief,
    build_decision_context,
    evidence_refs,
    render_decision_explanation,
    should_surface_decision,
)
from goals.ecosystem import recommend_ecosystem_tools
from goals.git_ops import source_commit
from goals.handoffs import analyze_handoff_owners
from goals.issues import analyze_goal_issues
from goals.memory import derive_memory_suggestions, load_memory
from goals.models import GoalArchitectureMap, GoalSnapshot
from goals.sources import analyze_source_freshness, unresolved_claims
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
    goal_brief = build_goal_brief(snapshot)
    waiting_on = _waiting_on(snapshot, surfaced_decisions, issue_report.user_questions)
    accepted_count = len([p for p in snapshot.phases if p.status == "accepted"])
    total_count = len(snapshot.phases)
    proof_count = len([p for p in snapshot.phases if p.evidence is not None])
    decision_brief = build_decision_brief(snapshot)
    brief = _goal_brief_html(goal_brief)
    phase_rows = "\n".join(
        f'<tr><td><span class="pill">{escape(p.phase_id)}</span></td>'
        f"<td><strong>{escape(p.title)}</strong><br><span>{escape(p.goal)}</span></td>"
        f"<td>{_status_label(str(p.status))}</td>"
        f"<td>{_evidence_summary(p.evidence.notes if p.evidence else '')}</td></tr>"
        for p in snapshot.phases
    )
    decisions = _decision_html(snapshot, surfaced_decisions, decision_brief)
    issues = _issues_html(issue_report)
    recommendations = _recommendations_html(snapshot)
    memory = _memory_html(snapshot)
    assets = _assets_html(snapshot)
    creative = _creative_html(snapshot)
    handoffs = _handoffs_html(snapshot)
    sources = _sources_html(snapshot)
    evidence = "\n".join(
        f"<li>{escape(p.phase_id)}: {escape((p.evidence.notes if p.evidence else 'No evidence yet'))}</li>"
        for p in snapshot.phases
    )
    architecture_html = _architecture_html(snapshot, architecture, architecture_path)
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
    .decision-brief {{ border: 1px solid var(--line); border-radius: 8px; padding: .9rem; margin-bottom: 1rem; background: var(--soft); }}
    .decision-brief .next {{ font-weight: 700; }}
    .decision .ask {{ color: var(--red); font-weight: 700; }}
    .decision-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: .75rem; margin-top: .75rem; }}
    .decision-card {{ border: 1px solid var(--line); border-radius: 8px; padding: .75rem; background: #fff; }}
    .decision-card p {{ margin-bottom: .35rem; }}
    .muted {{ color: var(--muted); }}
    .architecture-grid {{ display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); gap: 1rem; }}
    .architecture-brief {{ border: 1px solid var(--line); border-radius: 8px; padding: .9rem; margin-bottom: 1rem; background: var(--soft); }}
    .architecture-brief .review-focus {{ font-weight: 700; }}
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
    <a href="#brief">Brief</a>
    <a href="#progress">Progress</a>
    <a href="#issues">Issues</a>
    <a href="#decisions">Decisions</a>
    <a href="#ecosystem">Skills & Plugins</a>
    <a href="#memory">Memory</a>
    <a href="#architecture">Architecture</a>
    <a href="#creative">Creative</a>
    <a href="#handoffs">Handoffs</a>
    <a href="#evidence">Evidence</a>
    <a href="#assets">Assets</a>
    <a href="#sources">Sources</a>
    <a href="#technical">Technical Details</a>
  </nav>
  <section id="brief" class="panel">
    <h2>Goal Brief</h2>
    {brief}
  </section>
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
  <section id="creative" class="panel">
    <h2>Creative Variants</h2>
    {creative}
  </section>
  <section id="handoffs" class="panel">
    <h2>Handoff Owners</h2>
    {handoffs}
  </section>
  <section id="evidence" class="panel">
    <h2>Proof and Evidence</h2>
    <ul>{evidence}</ul>
  </section>
  <section id="assets" class="panel">
    <h2>Assets</h2>
    {assets}
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


def _goal_brief_html(brief) -> str:
    user_items = _brief_actions_html(
        brief.user_actions,
        empty="Nothing important is waiting on you.",
    )
    agent_items = _brief_actions_html(
        brief.agent_actions,
        empty="No agent-side repair action is currently suggested.",
    )
    technical = _bullets_html(brief.technical_details)
    return (
        '<div class="decision-brief">'
        f"<p>{escape(brief.summary)}</p>"
        f'<p><span class="pill">Waiting on: {escape(brief.waiting_on)}</span> '
        f'<span class="pill">Progress: {escape(brief.progress)}</span></p>'
        f"<p><strong>Proof:</strong> {escape(brief.proof)}</p>"
        "<h3>What Needs Your Answer</h3>"
        f"{user_items}"
        "<h3>What the Agent Can Do Next</h3>"
        f"{agent_items}"
        "<details><summary>Technical details</summary>"
        f"{technical}"
        "</details>"
        "</div>"
    )


def _brief_actions_html(actions, *, empty: str) -> str:
    if not actions:
        return f"<p>{escape(empty)}</p>"
    items = "".join(
        "<li>"
        f"<strong>{escape(action.title)}</strong>"
        f"<p>{escape(action.plain_summary)}</p>"
        f"<p><strong>Why it matters:</strong> {escape(action.why_it_matters)}</p>"
        + (
            f"<p><strong>Suggested reply or command:</strong> <code>{escape(action.suggested_reply)}</code></p>"
            if action.suggested_reply
            else ""
        )
        + (
            f"<p><strong>What happens next:</strong> {escape(action.what_happens_next)}</p>"
            if action.what_happens_next
            else ""
        )
        + "</li>"
        for action in actions[:5]
    )
    return f"<ul>{items}</ul>"


def _status_label(status: str) -> str:
    css = status.replace("_", "-")
    return f'<span class="status-label {escape(css)}">{escape(status)}</span>'


def _evidence_summary(notes: str) -> str:
    return escape(notes or "No evidence yet")


def _decision_html(snapshot: GoalSnapshot, surfaced_decisions: list, brief) -> str:
    brief_html = _decision_brief_html(brief)
    if not surfaced_decisions:
        if snapshot.decisions:
            return (
                f"{brief_html}"
                "<p>No important decisions are waiting on you. "
                "The agent can continue with recorded assumptions.</p>"
            )
        return f"{brief_html}<p>No decisions are waiting on you.</p>"
    context = build_decision_context(snapshot)
    items = []
    for decision in surfaced_decisions:
        explanation = render_decision_explanation(decision, context, level="detailed")
        summary = escape(decision.plain_summary)
        ask = escape(explanation.reason_for_surface)
        reply = escape(decision.suggested_reply or f"I choose: {decision.recommendation}")
        uncertainty = decision.uncertainty or context.known_gaps or []
        items.append(
            '<article class="decision">'
            f"<h3>{escape(decision.title)}</h3>"
            f"<p>{summary}</p>"
            f'<p class="ask">Why this needs you: {ask}</p>'
            f"<p><strong>Recommended option:</strong> {escape(decision.recommendation)}</p>"
            f"<p><strong>Suggested reply:</strong> <code>{reply}</code></p>"
            f"<p><strong>Confidence:</strong> {decision.confidence:.0%}</p>"
            f"{_decision_options_html(decision.options)}"
            f"{_decision_context_html(context)}"
            f"{_decision_uncertainty_html(uncertainty)}"
            f"{_decision_technical_html(decision.technical_details, evidence_refs(context))}"
            "</article>"
        )
    return brief_html + "\n".join(items)


def _decision_brief_html(brief) -> str:
    next_items = "".join(
        "<li>"
        f"<strong>{escape(item.title)}</strong>"
        f"<p>{escape(item.plain_summary)}</p>"
        f"<p><strong>Recommended:</strong> {escape(item.recommendation)}</p>"
        f"<p><strong>Suggested reply:</strong> <code>{escape(item.suggested_reply)}</code></p>"
        f'<p class="next">What happens next: {escape(item.what_happens_next)}</p>'
        "</li>"
        for item in brief.user_decisions
    )
    needs = (
        f"<ul>{next_items}</ul>" if next_items else "<p>Nothing important is waiting on you.</p>"
    )
    return (
        '<div class="decision-brief">'
        "<h3>Decision Brief</h3>"
        f"<p>{escape(brief.summary)}</p>"
        "<h4>What Needs Your Answer</h4>"
        f"{needs}"
        "<h4>What the Agent Can Handle</h4>"
        f"<p>{escape(brief.agent_handled_summary)}</p>"
        "</div>"
    )


def _decision_options_html(options) -> str:
    if not options:
        return "<p>No alternatives recorded.</p>"
    cards = []
    for option in options:
        tradeoffs = _bullets_html(option.tradeoffs or ["No tradeoffs recorded."])
        reversible = "yes" if option.reversible else "not clearly"
        reversal = (
            f"<p><strong>How to reverse:</strong> {escape(option.reversal_plan)}</p>"
            if option.reversal_plan
            else ""
        )
        cards.append(
            '<div class="decision-card">'
            f"<h4>{escape(option.label)}</h4>"
            f"<p>{escape(option.explanation)}</p>"
            f'<p><span class="pill">Risk: {escape(option.risk)}</span> '
            f'<span class="pill">Reversible: {reversible}</span></p>'
            f"<p><strong>Tradeoffs:</strong></p>{tradeoffs}"
            f"{reversal}"
            "</div>"
        )
    cards_html = "".join(cards)
    return f'<div class="decision-grid">{cards_html}</div>'


def _decision_context_html(context) -> str:
    points = []
    if context.accepted_phases:
        points.append(f"Accepted phases: {', '.join(context.accepted_phases[:4])}")
    if context.checks_run:
        points.append(f"Checks run: {', '.join(context.checks_run[:4])}")
    if context.changed_files:
        points.append(f"Changed files: {', '.join(context.changed_files[:4])}")
    if context.source_claims:
        points.append(f"Source-backed claims: {', '.join(context.source_claims[:3])}")
    if context.learnings:
        points.append(f"Learnings: {', '.join(context.learnings[:3])}")
    if not points:
        points.append("No prior goal context recorded yet.")
    return "<h4>What we know so far</h4>" + _bullets_html(points)


def _decision_uncertainty_html(items: list[str]) -> str:
    if not items:
        return '<p class="muted">No major uncertainty recorded.</p>'
    return "<h4>Uncertainty</h4>" + _bullets_html(items)


def _decision_technical_html(details: str, refs: list[str]) -> str:
    technical = escape(details or "No technical details recorded.")
    ref_html = _bullets_html(refs or ["No evidence references recorded."])
    return (
        "<details>"
        "<summary>Technical details and evidence</summary>"
        f"<p>{technical}</p>"
        f"{ref_html}"
        "</details>"
    )


def _bullets_html(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


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
    if not snapshot.sources and not snapshot.source_claims:
        return "<h3>Citation Quality</h3><p>No sources recorded yet.</p><h3>Freshness</h3><p>No sources recorded yet.</p>"
    freshness = analyze_source_freshness(snapshot)
    citations = analyze_citation_quality(snapshot)
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
    freshness_items = "".join(
        "<li>"
        f"<strong>{escape(finding.summary)}</strong>"
        f"<p>{escape(finding.detail)}</p>"
        + (
            f"<p><strong>Next:</strong> {escape(finding.suggested_action)}</p>"
            if finding.suggested_action
            else ""
        )
        + "</li>"
        for finding in freshness.findings[:5]
    )
    freshness_html = (
        f"<p>{escape(freshness.summary)}</p><ul>{freshness_items}</ul>"
        if freshness.findings
        else f"<p>{escape(freshness.summary)}</p>"
    )
    citation_items = "".join(
        "<li>"
        f"<strong>{escape(finding.summary)}</strong>"
        f"<p>{escape(finding.detail)}</p>"
        + (
            f"<p><strong>Next:</strong> {escape(finding.suggested_action)}</p>"
            if finding.suggested_action
            else ""
        )
        + "</li>"
        for finding in citations.findings[:5]
    )
    citation_html = (
        f"<p>{escape(citations.summary)}</p><ul>{citation_items}</ul>"
        if citations.findings
        else f"<p>{escape(citations.summary)}</p>"
    )
    return (
        f"{warning}<h3>Citation Quality</h3>{citation_html}<h3>Freshness</h3>{freshness_html}"
        f'<h3>Recorded Sources</h3><ul class="node-list">{source_items}</ul>'
        f"<h3>Source-backed Claims</h3><ul>{claim_items or '<li>No claims recorded yet.</li>'}</ul>"
    )


def _assets_html(snapshot: GoalSnapshot) -> str:
    if not snapshot.assets:
        return "<h3>Provenance</h3><p>No assets recorded yet.</p>"
    report = analyze_asset_provenance(snapshot)
    asset_items = "\n".join(
        "<li>"
        f"<strong>{escape(asset.title)}</strong>"
        f"<p>{escape(asset.notes or asset.locator or 'No note recorded.')}</p>"
        f'<span class="pill">{escape(asset.asset_type)}</span> '
        f'<span class="pill">{escape(asset.origin)}</span> '
        f'<span class="status-label {escape(asset.usage_rights)}">{escape(asset.usage_rights)}</span>'
        + (f"<p>License: {escape(asset.license)}</p>" if asset.license else "")
        + "</li>"
        for asset in snapshot.assets
    )
    finding_items = "".join(
        "<li>"
        f"<strong>{escape(finding.summary)}</strong>"
        f"<p>{escape(finding.detail)}</p>"
        + (
            f"<p><strong>Next:</strong> {escape(finding.suggested_action)}</p>"
            if finding.suggested_action
            else ""
        )
        + "</li>"
        for finding in report.findings[:5]
    )
    provenance_html = (
        f"<p>{escape(report.summary)}</p><ul>{finding_items}</ul>"
        if report.findings
        else f"<p>{escape(report.summary)}</p>"
    )
    return (
        f"<h3>Provenance</h3>{provenance_html}"
        f'<h3>Recorded Assets</h3><ul class="node-list">{asset_items}</ul>'
    )


def _creative_html(snapshot: GoalSnapshot) -> str:
    report = analyze_creative_variants(snapshot)
    if not snapshot.creative_variants:
        return "<h3>Comparison</h3><p>No creative variants recorded yet.</p>"
    recommended = report.recommended_variant_id or "none"
    variant_items = "\n".join(
        "<li>"
        f"<strong>{escape(variant.title)}</strong>"
        f"<p>{escape(variant.summary or 'No summary recorded.')}</p>"
        f'<span class="pill">{escape(variant.variant_id)}</span> '
        f'<span class="status-label {escape(variant.status)}">{escape(variant.status)}</span>'
        + (
            f"<p><strong>Best for:</strong> {escape(variant.best_for)}</p>"
            if variant.best_for
            else ""
        )
        + (
            f"<p><strong>Scores:</strong> {escape(_score_text(variant.scores))}</p>"
            if variant.scores
            else ""
        )
        + (
            f"<p><strong>Assets:</strong> {escape(', '.join(variant.asset_ids))}</p>"
            if variant.asset_ids
            else ""
        )
        + "</li>"
        for variant in snapshot.creative_variants
    )
    finding_items = "".join(
        "<li>"
        f"<strong>{escape(finding.summary)}</strong>"
        f"<p>{escape(finding.detail)}</p>"
        + (
            f"<p><strong>Next:</strong> {escape(finding.suggested_action)}</p>"
            if finding.suggested_action
            else ""
        )
        + "</li>"
        for finding in report.findings[:5]
    )
    findings_html = (
        f"<p>{escape(report.summary)}</p><ul>{finding_items}</ul>"
        if report.findings
        else f"<p>{escape(report.summary)}</p>"
    )
    return (
        f"<h3>Comparison</h3>{findings_html}"
        f"<p><strong>Recommended variant:</strong> <code>{escape(recommended)}</code></p>"
        f'<h3>Recorded Variants</h3><ul class="node-list">{variant_items}</ul>'
    )


def _handoffs_html(snapshot: GoalSnapshot) -> str:
    report = analyze_handoff_owners(snapshot)
    if not snapshot.handoff_owners:
        return "<h3>Owner Registry</h3><p>No handoff owners recorded yet.</p>"
    owner_items = "\n".join(
        "<li>"
        f"<strong>{escape(owner.label)}</strong>"
        f"<p>{escape(owner.responsibility or owner.notes or 'No responsibility recorded.')}</p>"
        f'<span class="pill">{escape(owner.owner_id)}</span> '
        f'<span class="pill">{escape(owner.owner_type)}</span> '
        f'<span class="status-label {escape(owner.status)}">{escape(owner.status)}</span> '
        f'<span class="pill">confirmation: {escape(owner.confirmation)}</span>'
        + (f"<p><strong>Role:</strong> {escape(owner.role)}</p>" if owner.role else "")
        + (
            f"<p><strong>Phases:</strong> {escape(', '.join(owner.phase_ids))}</p>"
            if owner.phase_ids
            else ""
        )
        + (
            f"<p><strong>Escalation:</strong> {escape(owner.escalation_path)}</p>"
            if owner.escalation_path
            else ""
        )
        + "</li>"
        for owner in snapshot.handoff_owners
    )
    finding_items = "".join(
        "<li>"
        f"<strong>{escape(finding.summary)}</strong>"
        f"<p>{escape(finding.detail)}</p>"
        + (
            f"<p><strong>Next:</strong> {escape(finding.suggested_action)}</p>"
            if finding.suggested_action
            else ""
        )
        + "</li>"
        for finding in report.findings[:5]
    )
    findings_html = (
        f"<p>{escape(report.summary)}</p><ul>{finding_items}</ul>"
        if report.findings
        else f"<p>{escape(report.summary)}</p>"
    )
    return (
        f"<h3>Owner Registry</h3>{findings_html}"
        f'<h3>Recorded Owners</h3><ul class="node-list">{owner_items}</ul>'
    )


def _architecture_html(
    snapshot: GoalSnapshot,
    architecture: GoalArchitectureMap,
    architecture_path: Path | None,
) -> str:
    counts = architecture_status_counts(architecture)
    brief = build_architecture_brief(architecture)
    check = analyze_code_architecture(snapshot, Path(snapshot.topology.worktree_path))
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
    brief_html = _architecture_brief_html(brief)
    check_items = "".join(
        "<li>"
        f"<strong>{escape(finding.summary)}</strong>"
        f"<p>{escape(finding.detail)}</p>"
        + (
            f"<p><strong>Next:</strong> {escape(finding.suggested_action)}</p>"
            if finding.suggested_action
            else ""
        )
        + "</li>"
        for finding in check.findings[:5]
    )
    check_html = (
        f"<p>{escape(check.summary)}</p><ul>{check_items}</ul>"
        if check.findings
        else f"<p>{escape(check.summary)}</p>"
    )
    return f"""
    <p class="plain">{escape(architecture.overview)}</p>
    {brief_html}
    <h3>Code-Derived Check</h3>
    {check_html}
    <p><strong>Status counts:</strong> {count_text}</p>
    {link}
    <div class="architecture-grid">
      <ul class="node-list">{nodes}</ul>
      <pre class="diagram">{escape(render_mermaid(architecture))}</pre>
    </div>
    """


def _architecture_brief_html(brief) -> str:
    focus_items = _bullets_html(brief.review_focus or ["No architecture review focus recorded."])
    gap_items = _bullets_html(
        [f"{item.label}: {item.review_focus}" for item in brief.evidence_gaps]
        or ["No architecture evidence gaps detected."]
    )
    question_items = _bullets_html(
        brief.open_questions or ["No open architecture questions recorded."]
    )
    return (
        '<div class="architecture-brief">'
        "<h3>Architecture Brief</h3>"
        f"<p>{escape(brief.summary)}</p>"
        '<p class="review-focus">Review focus</p>'
        f"{focus_items}"
        "<details><summary>Evidence gaps and open questions</summary>"
        "<h4>Evidence Gaps</h4>"
        f"{gap_items}"
        "<h4>Open Questions</h4>"
        f"{question_items}"
        "</details>"
        "</div>"
    )


def _score_text(scores) -> str:
    return ", ".join(
        f"{score.criterion} {score.score}/5" + (f" ({score.rationale})" if score.rationale else "")
        for score in scores
    )
