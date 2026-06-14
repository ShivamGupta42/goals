from __future__ import annotations

from html import escape
from pathlib import Path

from goals.architecture import (
    analyze_code_architecture,
    architecture_for_snapshot,
    architecture_status_counts,
    build_architecture_brief,
)
from goals.brief import build_goal_brief
from goals.checkpoints import build_current_checkpoint_brief
from goals.decisions import should_surface_decision
from goals.git_ops import source_commit
from goals.issues import analyze_goal_issues
from goals.models import GoalArchitectureMap, GoalSnapshot
from goals.sources import analyze_source_freshness, unresolved_claims
from goals.storage import atomic_write_text

# Warm-editorial palette, shared by the page CSS and the inline SVG diagram.
_PAPER = "#fffdf9"
_INK = "#2c2722"
_EDGE = "#9a958c"
_NODE_STROKE = {
    "built": "#5f7256",
    "in_progress": "#b06a4f",
    "blocked": "#b42318",
    "planned": "#9a7b3f",
    "deferred": "#9a958c",
    "removed": "#c4bcae",
}
_STEP_ICON = {
    "accepted": "✓",
    "built": "✓",
    "complete": "✓",
    "in_progress": "→",
    "needs_review": "→",
    "active": "→",
    "blocked": "⚠",
    "pending": "○",
    "planned": "○",
}
_STEP_LABEL = {
    "accepted": "Done",
    "in_progress": "In progress",
    "needs_review": "In review",
    "blocked": "Blocked",
    "pending": "Not started",
}


def render_dashboard(
    snapshot: GoalSnapshot,
    output_path: Path,
    *,
    architecture: GoalArchitectureMap | None = None,
    architecture_path: Path | None = None,
) -> None:
    """Render the read-only goal dashboard.

    This is a project *overview* — what's done and what's happening — not an
    interactive surface. Decisions are made in the agent conversation and shown
    here as a judgement log; the page never asks the user to act on it directly.
    """
    architecture = architecture or architecture_for_snapshot(snapshot)
    brief = build_goal_brief(snapshot)
    checkpoint = build_current_checkpoint_brief(snapshot)
    issue_report = analyze_goal_issues(snapshot)

    accepted = len([p for p in snapshot.phases if str(p.status) == "accepted"])
    total = len(snapshot.phases)
    proof = len([p for p in snapshot.phases if p.evidence is not None])
    pct = round(accepted / total * 100) if total else 0
    open_questions = _open_questions(snapshot, issue_report)

    needs_you = _needs_you_html(brief, open_questions)
    steps = _steps_html(snapshot)
    evidence = _evidence_detail_html(snapshot, checkpoint)
    arch_html = _architecture_detail_html(snapshot, architecture, architecture_path)
    decisions = _decisions_log_html(snapshot)
    issues = _issues_html(issue_report)
    sources = _sources_html(snapshot)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Goal — {escape(snapshot.goal_id)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --paper:#faf7f1; --ink:#2c2722; --soft:#736b60; --line:#e6dfd3; --hair:#efe9de;
      --sage:#5f7256; --clay:#b06a4f; --gold:#9a7b3f; --card:#fffdf9; --chip:#f1ebe0; --focus:#b06a4f;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink);
      font-family:"Hanken Grotesk",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
      font-size:17px; line-height:1.6; -webkit-font-smoothing:antialiased; overflow-wrap:break-word; }}
    .wrap {{ max-width:700px; margin:0 auto; padding:3.5rem 1.5rem 6rem; }}
    a {{ color:var(--clay); }}
    .skip-link {{ position:absolute; left:-999px; top:0; background:var(--ink); color:var(--paper); padding:.6rem 1rem; border-radius:0 0 8px 0; z-index:10; }}
    .skip-link:focus {{ left:0; }}
    a:focus-visible, summary:focus-visible, [tabindex]:focus-visible {{ outline:3px solid var(--focus); outline-offset:2px; border-radius:6px; }}
    main:focus {{ outline:none; }}
    .kicker {{ font-size:.72rem; letter-spacing:.16em; text-transform:uppercase; color:var(--clay); font-weight:700;
      margin:0 0 1.3rem; display:flex; align-items:center; gap:.55rem; }}
    .kicker .dot {{ width:7px; height:7px; border-radius:50%; background:var(--sage); box-shadow:0 0 0 4px rgba(95,114,86,.15); }}
    h1 {{ font-weight:800; font-size:clamp(1.9rem,5.2vw,2.9rem); line-height:1.09; letter-spacing:-.02em; margin:0 0 .8rem; overflow-wrap:anywhere; }}
    .why {{ font-size:1.08rem; color:var(--soft); max-width:52ch; margin:0 0 2.2rem; }}
    .meter {{ display:flex; align-items:baseline; gap:.9rem; margin:0 0 .5rem; }}
    .meter .big {{ font-size:1.6rem; font-weight:800; letter-spacing:-.01em; }}
    .meter .small {{ color:var(--soft); font-size:.92rem; }}
    .rule {{ height:7px; border-radius:7px; background:var(--line); overflow:hidden; margin:.2rem 0 2.1rem; }}
    .rule > i {{ display:block; height:100%; background:linear-gradient(90deg,var(--sage),var(--gold)); }}
    .facts {{ display:flex; flex-wrap:wrap; gap:.4rem 1.8rem; border-top:1px solid var(--line); border-bottom:1px solid var(--line);
      padding:.85rem 0; margin:0 0 2.4rem; font-size:.92rem; }}
    .facts b {{ font-weight:700; }} .facts span {{ color:var(--soft); }}
    .note {{ border-left:3px solid var(--clay); background:var(--card); padding:1.1rem 1.35rem; border-radius:0 12px 12px 0; margin:0 0 1rem; }}
    .note h2 {{ font-size:1.08rem; font-weight:700; margin:0 0 .45rem; }}
    .note p {{ margin:.3rem 0; }} .note .ask {{ color:var(--clay); font-size:.92rem; }}
    h2.sec {{ font-size:.74rem; letter-spacing:.14em; text-transform:uppercase; color:var(--soft); font-weight:700; margin:2.6rem 0 1.1rem; }}
    .steps {{ list-style:none; margin:0; padding:0; }}
    .steps li {{ display:grid; grid-template-columns:auto 1fr auto; gap:1rem; align-items:baseline; padding:.95rem 0; border-bottom:1px solid var(--hair); }}
    .steps .mark {{ font-weight:800; width:1.5rem; font-size:1.05rem; }}
    .steps .ttl {{ font-weight:700; font-size:1.02rem; }}
    .steps .sub {{ color:var(--soft); font-size:.88rem; display:block; }}
    .steps .st {{ font-size:.74rem; letter-spacing:.04em; text-transform:uppercase; color:var(--soft); white-space:nowrap; font-weight:600; }}
    .done .mark {{ color:var(--sage); }} .doing .mark, .doing .st {{ color:var(--clay); }} .blocked .mark, .blocked .st {{ color:#b42318; }}
    details {{ border-top:1px solid var(--line); }}
    details summary {{ font-size:.96rem; font-weight:700; padding:1.05rem 0; cursor:pointer; list-style:none; display:flex; align-items:center; color:var(--ink); }}
    details summary::-webkit-details-marker {{ display:none; }}
    details summary .meta {{ color:var(--soft); font-size:.78rem; font-weight:500; margin-left:auto; margin-right:1rem; }}
    details summary::after {{ content:"+"; color:var(--clay); font-weight:700; }}
    details[open] summary::after {{ content:"–"; }}
    .body {{ padding:0 0 1.6rem; font-size:.95rem; }} .body > p {{ margin:.3rem 0 .9rem; color:var(--soft); }}
    .kv {{ list-style:none; padding:0; margin:.3rem 0; display:grid; gap:.5rem; }}
    .kv li {{ border:1px solid var(--line); border-radius:10px; padding:.6rem .85rem; background:var(--card); }}
    .kv .t {{ font-weight:700; }} .kv .d {{ color:var(--soft); font-size:.86rem; }}
    .chip {{ display:inline-block; background:var(--chip); border-radius:999px; padding:.08rem .5rem; margin-left:.3rem; font-size:.7rem; font-weight:600; }}
    .nodes {{ list-style:none; padding:0; margin:.4rem 0 1rem; display:grid; gap:.5rem; }}
    .nodes li {{ display:flex; gap:.7rem; align-items:baseline; border:1px solid var(--line); border-radius:10px; padding:.6rem .85rem; background:var(--card); }}
    .nodes .nm {{ font-weight:700; }} .nodes .nd {{ color:var(--soft); font-size:.85rem; }}
    .nodes .stt {{ margin-left:auto; font-size:.7rem; letter-spacing:.03em; text-transform:uppercase; white-space:nowrap; font-weight:700; }}
    .built {{ color:var(--sage); }} .in-progress {{ color:var(--clay); }} .planned, .deferred {{ color:var(--gold); }} .blocked {{ color:#b42318; }}
    .diagram-wrap {{ border:1px solid var(--line); border-radius:12px; background:var(--card); padding:1rem; margin:.5rem 0 .9rem; }}
    .diagram-wrap svg {{ width:100%; height:auto; display:block; }}
    .cap {{ color:var(--soft); font-size:.82rem; margin:.3rem 0 1rem; text-align:center; }}
    code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--chip); padding:.06rem .35rem; border-radius:5px; font-size:.85em; overflow-wrap:anywhere; }}
    svg text {{ font-family:"Hanken Grotesk",-apple-system,system-ui,sans-serif; }}
    footer {{ margin-top:2.8rem; color:var(--soft); font-size:.8rem; letter-spacing:.03em; }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="wrap">
    <p class="kicker"><span class="dot"></span>Goal · {escape(snapshot.status)}</p>
    <h1>{escape(snapshot.objective)}</h1>
    <p class="why">{escape(snapshot.why or "A long-running task, kept understandable and resumable.")}</p>

    <div class="meter"><span class="big">{accepted} of {total}</span><span class="small">steps accepted · {escape(brief.progress)}</span></div>
    <div class="rule"><i style="width:{pct}%"></i></div>
    <p class="facts">
      <span>Waiting on</span> <b>{escape(brief.waiting_on)}</b> &nbsp;·&nbsp;
      <span>Proof</span> <b>{proof} / {total} steps</b> &nbsp;·&nbsp;
      <span>Updated</span> <b>{escape(snapshot.last_updated)}</b>
    </p>

    <main id="main" tabindex="-1">
    {needs_you}

    <h2 class="sec">The steps</h2>
    <ul class="steps">{steps}</ul>

    <h2 class="sec">Detail</h2>
    <details><summary>Proof &amp; evidence<span class="meta">{proof} of {total} recorded</span></summary>
      <div class="body">{evidence}</div>
    </details>
    <details><summary>Architecture map<span class="meta">{_arch_meta(architecture)}</span></summary>
      <div class="body">{arch_html}</div>
    </details>
    <details><summary>Decisions<span class="meta">{_decisions_meta(snapshot)}</span></summary>
      <div class="body">{decisions}</div>
    </details>
    <details><summary>Issues<span class="meta">{_issues_meta(issue_report)}</span></summary>
      <div class="body">{issues}</div>
    </details>
    <details><summary>Sources<span class="meta">{_sources_meta(snapshot)}</span></summary>
      <div class="body">{sources}</div>
    </details>
    <details><summary>Technical details</summary>
      <div class="body">
        <p>Goal ID: <code>{escape(snapshot.goal_id)}</code> · Event offset: <code>{snapshot.event_count}</code> ·
        Source commit: <code>{escape(source_commit(Path(snapshot.topology.worktree_path)))}</code></p>
        <p>Read-only, generated by Goals from sanitized snapshot state.</p>
      </div>
    </details>
    </main>
    <footer>Generated by Goals · read-only</footer>
  </div>
</body>
</html>
"""
    atomic_write_text(output_path, html)


def _open_questions(snapshot: GoalSnapshot, issue_report) -> list[str]:
    titles = [d.title for d in snapshot.decisions if should_surface_decision(d)[0]]
    titles.extend(q for q in issue_report.user_questions if q not in titles)
    return titles


def _needs_you_html(brief, open_questions: list[str]) -> str:
    if str(brief.waiting_on).lower() != "you" and not open_questions:
        return ""
    if open_questions:
        items = "".join(f"<li>{escape(q)}</li>" for q in open_questions[:5])
        body = f"<ul>{items}</ul>"
    else:
        body = "<p>The agent is paused until you weigh in.</p>"
    return (
        '<div class="note"><h2>Waiting on you</h2>'
        f'<p class="ask">Open question(s) — answer in the conversation; the agent records the call here.</p>'
        f"{body}</div>"
    )


def _steps_html(snapshot: GoalSnapshot) -> str:
    rows = []
    for phase in snapshot.phases:
        status = str(phase.status)
        cls = _step_class(status)
        icon = _STEP_ICON.get(status, "○")
        label = _STEP_LABEL.get(status, status.replace("_", " "))
        rows.append(
            f'<li class="{cls}"><span class="mark" aria-hidden="true">{icon}</span>'
            f'<span><span class="ttl">{escape(phase.title)}</span>'
            f'<span class="sub">{escape(phase.goal)}</span></span>'
            f'<span class="st">{escape(label)}</span></li>'
        )
    return "".join(rows)


def _step_class(status: str) -> str:
    if status in {"accepted", "built", "complete"}:
        return "done"
    if status in {"in_progress", "needs_review", "active"}:
        return "doing"
    if status == "blocked":
        return "blocked"
    return "todo"


def _evidence_detail_html(snapshot: GoalSnapshot, checkpoint) -> str:
    items = []
    for phase in snapshot.phases:
        if phase.evidence:
            detail = escape(phase.evidence.notes or "Evidence recorded.")
        else:
            detail = f"{escape(phase.phase_id)} has no evidence yet."
        items.append(
            f'<li><span class="t">{escape(phase.phase_id)} · {escape(phase.title)}</span>'
            f'<br><span class="d">{detail}</span></li>'
        )
    checkpoint_html = ""
    if checkpoint and checkpoint.phase_id:
        title = escape(checkpoint.checkpoint_title or "Phase evidence and review")
        what = escape(checkpoint.what_changed or "")
        refs = [*checkpoint.evidence_refs, *checkpoint.decision_refs]
        refs_html = (
            " · Refs: " + ", ".join(escape(ref) for ref in refs) if refs else ""
        )
        checkpoint_html = (
            f'<p><strong>Current checkpoint:</strong> {title}'
            f'{(" — " + what) if what else ""}{refs_html}</p>'
        )
    return f'<ul class="kv">{"".join(items)}</ul>{checkpoint_html}'


def _architecture_detail_html(
    snapshot: GoalSnapshot,
    architecture: GoalArchitectureMap,
    architecture_path: Path | None,
) -> str:
    if not architecture.nodes:
        return "<p>No architecture recorded yet.</p>"
    arch_brief = build_architecture_brief(architecture)
    check = analyze_code_architecture(snapshot, Path(snapshot.topology.worktree_path))
    diagram = _architecture_svg(architecture)
    cap = (
        '<p class="cap">Built outlined in sage · in progress in clay · planned in gold</p>'
        if diagram
        else ""
    )
    extra = (
        f"<p>Showing 8 of {len(architecture.nodes)} nodes — full set below.</p>"
        if len(architecture.nodes) > 8
        else ""
    )
    nodes = "".join(
        f'<li><span><span class="nm">{escape(node.label)}</span>'
        f'<br><span class="nd">{escape(node.plain_summary)}</span></span>'
        f'<span class="stt {escape(node.status.replace("_", "-"))}">'
        f'{escape(node.status.replace("_", " "))}</span></li>'
        for node in architecture.nodes
    )
    focus = arch_brief.review_focus[0] if arch_brief.review_focus else ""
    focus_html = f"<p><strong>Review focus:</strong> {escape(focus)}</p>" if focus else ""
    check_html = f"<p>{escape(check.summary)}</p>" if check.summary else ""
    return (
        f'<p>{escape(architecture.overview)}</p>'
        f"{diagram}{cap}{extra}"
        f'<ul class="nodes">{nodes}</ul>'
        f"{focus_html}{check_html}"
    )


def _architecture_svg(architecture: GoalArchitectureMap) -> str:
    """A neat, dependency-free SVG flow built from the architecture nodes/edges.

    Nodes are placed in layers by longest-path depth so a small DAG reads
    left-to-right; the text node list below is the accessible equivalent.
    """
    nodes = architecture.nodes[:8]
    if not nodes:
        return ""
    ids = {node.node_id for node in nodes}
    adjacency: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for edge in architecture.edges:
        if edge.from_node in ids and edge.to_node in ids:
            adjacency[edge.from_node].append(edge.to_node)
    layer = {node.node_id: 0 for node in nodes}
    for _ in range(len(nodes)):
        changed = False
        for node in nodes:
            for target in adjacency[node.node_id]:
                if layer[target] < layer[node.node_id] + 1:
                    layer[target] = layer[node.node_id] + 1
                    changed = True
        if not changed:
            break
    columns: dict[int, list] = {}
    for node in nodes:
        columns.setdefault(layer[node.node_id], []).append(node)

    box_w, box_h, h_gap, v_gap, pad = 168, 54, 50, 20, 12
    col_keys = sorted(columns)
    max_rows = max(len(group) for group in columns.values())
    width = pad * 2 + len(col_keys) * box_w + (len(col_keys) - 1) * h_gap
    height = pad * 2 + max_rows * box_h + (max_rows - 1) * v_gap
    position: dict[str, tuple[float, float]] = {}
    for index, key in enumerate(col_keys):
        group = columns[key]
        col_x = pad + index * (box_w + h_gap)
        col_h = len(group) * box_h + (len(group) - 1) * v_gap
        start_y = (height - col_h) / 2
        for row, node in enumerate(group):
            position[node.node_id] = (col_x, start_y + row * (box_h + v_gap))

    edge_paths = []
    for edge in architecture.edges:
        if edge.from_node in position and edge.to_node in position:
            x1, y1 = position[edge.from_node]
            x2, y2 = position[edge.to_node]
            edge_paths.append(
                f'<path d="M{x1 + box_w:.0f},{y1 + box_h / 2:.0f} '
                f'L{x2:.0f},{y2 + box_h / 2:.0f}"/>'
            )
    node_svg = []
    for node in nodes:
        x, y = position[node.node_id]
        stroke = _NODE_STROKE.get(node.status, _NODE_STROKE["planned"])
        cx = x + box_w / 2
        node_svg.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{box_w}" height="{box_h}" rx="12" '
            f'fill="{_PAPER}" stroke="{stroke}" stroke-width="1.6"/>'
            f'<text x="{cx:.0f}" y="{y + box_h / 2 - 2:.0f}" text-anchor="middle" '
            f'font-size="14" font-weight="700" fill="{_INK}">{escape(_truncate(node.label, 22))}</text>'
            f'<text x="{cx:.0f}" y="{y + box_h / 2 + 15:.0f}" text-anchor="middle" '
            f'font-size="11" fill="{stroke}">{escape(node.status.replace("_", " "))}</text>'
        )
    return (
        f'<div class="diagram-wrap"><svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" '
        f'aria-label="{escape(architecture.overview or "Architecture diagram")}">'
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{_EDGE}"/></marker></defs>'
        f'<g fill="none" stroke="{_EDGE}" stroke-width="1.5" marker-end="url(#ah)">'
        f'{"".join(edge_paths)}</g>'
        f'<g>{"".join(node_svg)}</g></svg></div>'
    )


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _decisions_log_html(snapshot: GoalSnapshot) -> str:
    if not snapshot.judgements:
        return "<p>No decisions recorded yet.</p>"
    items = []
    for judgement in snapshot.judgements[:12]:
        reversible = "reversible" if judgement.reversible else "irreversible"
        rationale = (
            f'<br><span class="d">{escape(judgement.rationale)}</span>'
            if judgement.rationale
            else ""
        )
        items.append(
            f'<li><span class="t">{escape(judgement.question)}</span>'
            f'<br><span class="d">Chose: {escape(judgement.choice)}'
            f'<span class="chip">{escape(judgement.decided_by)}</span>'
            f'<span class="chip">{reversible}</span></span>{rationale}</li>'
        )
    return f'<ul class="kv">{"".join(items)}</ul>'


def _issues_html(report) -> str:
    if not report.issues:
        return "<p>No blocking issues found.</p>"
    items = "".join(
        f'<li><span class="t">{escape(issue.summary)}'
        f'<span class="chip">{escape(issue.severity)}</span></span>'
        + (f'<br><span class="d">{escape(issue.detail)}</span>' if issue.detail else "")
        + (
            f'<br><span class="d">Next: {escape(issue.suggested_action)}</span>'
            if issue.suggested_action
            else ""
        )
        + "</li>"
        for issue in report.issues[:8]
    )
    return f'<p>{escape(report.summary)}</p><ul class="kv">{items}</ul>'


def _sources_html(snapshot: GoalSnapshot) -> str:
    if not snapshot.sources and not snapshot.source_claims:
        return "<p>No sources recorded yet.</p>"
    freshness = analyze_source_freshness(snapshot)
    unresolved = unresolved_claims(snapshot)
    warning = (
        f"<p>{len(unresolved)} claim(s) need source cleanup.</p>"
        if unresolved
        else f"<p>{escape(freshness.summary)}</p>"
    )
    sources = "".join(
        f'<li><span class="t">{escape(source.title)}'
        f'<span class="chip">{escape(source.credibility)}</span></span>'
        f'<br><span class="d">{escape(source.summary or source.locator or "No summary recorded.")}</span></li>'
        for source in snapshot.sources[:8]
    )
    claims = "".join(
        f'<li><span class="t">{escape(claim.claim)}</span>'
        f'<br><span class="d">Confidence: {claim.confidence:.0%}</span></li>'
        for claim in snapshot.source_claims[:8]
    )
    sources_html = f'<ul class="kv">{sources}</ul>' if sources else ""
    claims_html = f'<ul class="kv">{claims}</ul>' if claims else ""
    return f"{warning}{sources_html}{claims_html}"


def _arch_meta(architecture: GoalArchitectureMap) -> str:
    counts = architecture_status_counts(architecture)
    if not counts:
        return "none yet"
    return " · ".join(f"{status.replace('_', ' ')} {count}" for status, count in sorted(counts.items()))


def _decisions_meta(snapshot: GoalSnapshot) -> str:
    count = len(snapshot.judgements)
    return "none yet" if not count else f"{count} recorded"


def _issues_meta(report) -> str:
    return "clear" if not report.issues else f"{len(report.issues)} open"


def _sources_meta(snapshot: GoalSnapshot) -> str:
    count = len(snapshot.sources)
    return "none yet" if not count else f"{count} source(s)"
