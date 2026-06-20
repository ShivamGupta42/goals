from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from goals.architecture import (
    analyze_code_architecture,
    architecture_for_snapshot,
    architecture_status_counts,
    build_architecture_brief,
)
from goals.audit import build_phase_lineage
from goals.brief import build_goal_brief
from goals.checkpoints import build_current_checkpoint_brief
from goals.decisions import should_surface_decision
from goals.git_ops import source_commit
from goals.issues import analyze_goal_issues
from goals.journey import sort_assumptions
from goals.models import Event, GoalArchitectureMap, GoalSnapshot
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
    events: list[Event] | None = None,
) -> None:
    """Render the read-only goal dashboard.

    This is a project *overview* — what's done and what's happening — not an
    interactive surface. Decisions are made in the agent conversation and shown
    here as a judgement log; the page never asks the user to act on it directly.
    """
    # An architecture map is "recorded" when an agent supplied one — either via
    # the explicit arg (callers/tests) or stored on the snapshot. Otherwise the
    # map is a phase-derived placeholder we hide as noise.
    has_recorded_architecture = architecture is not None or snapshot.architecture is not None
    architecture = architecture or architecture_for_snapshot(snapshot)
    brief = build_goal_brief(snapshot)
    checkpoint = build_current_checkpoint_brief(snapshot)
    issue_report = analyze_goal_issues(snapshot)

    accepted = len([p for p in snapshot.phases if str(p.status) == "accepted"])
    total = len(snapshot.phases)
    proof = len([p for p in snapshot.phases if p.evidence is not None])
    pct = round(accepted / total * 100) if total else 0
    open_questions = _open_questions(snapshot, issue_report)

    full_goal = _full_goal_html(snapshot.objective)
    status_banner = _status_banner_html(snapshot, brief, checkpoint, open_questions)
    produced = _produced_html(checkpoint)
    steps = _steps_html(snapshot)
    journey_section = _journey_html(snapshot)
    decisions_teaser = _decisions_teaser_html(snapshot)
    issues_section = _issues_section_html(issue_report)
    evidence = _evidence_detail_html(snapshot, checkpoint)
    lineage_section = _lineage_section_html(snapshot, events or [])
    architecture_section = _architecture_section_html(
        snapshot, architecture, architecture_path, has_recorded_architecture
    )
    sources_section = _sources_section_html(snapshot)

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
    h1 {{ font-weight:800; font-size:clamp(1.9rem,5.2vw,2.9rem); line-height:1.09; letter-spacing:-.02em; margin:0 0 .5rem; overflow-wrap:anywhere; }}
    h1.title {{ display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
    .full-goal {{ margin:0 0 .9rem; }}
    .full-goal summary {{ font-size:.84rem; font-weight:600; color:var(--clay); cursor:pointer; list-style:none; display:inline-flex; align-items:center; gap:.35rem; }}
    .full-goal summary::-webkit-details-marker {{ display:none; }}
    .full-goal summary::before {{ content:"▸"; font-size:.7rem; }}
    .full-goal[open] summary::before {{ content:"▾"; }}
    .full-goal p {{ font-size:1rem; color:var(--ink); margin:.55rem 0 0; max-width:60ch; overflow-wrap:anywhere; }}
    .journey {{ font-size:1.06rem; color:var(--ink); opacity:.82; max-width:54ch; margin:0 0 .55rem; }}
    .orient {{ font-size:.86rem; color:var(--soft); margin:0 0 2.1rem; opacity:.85; }}
    .meter {{ display:flex; align-items:baseline; gap:.9rem; margin:0 0 .5rem; }}
    .meter .big {{ font-size:1.6rem; font-weight:800; letter-spacing:-.01em; }}
    .meter .small {{ color:var(--soft); font-size:.92rem; }}
    .rule {{ height:7px; border-radius:7px; background:var(--line); overflow:hidden; margin:.2rem 0 2.1rem; }}
    .rule > i {{ display:block; height:100%; background:linear-gradient(90deg,var(--sage),var(--gold)); }}
    .facts {{ display:flex; flex-wrap:wrap; gap:.5rem 1.6rem; border-top:1px solid var(--line); border-bottom:1px solid var(--line);
      padding:.9rem 0; margin:0 0 2.4rem; font-size:.9rem; }}
    .facts .fact {{ display:inline-flex; align-items:baseline; gap:.45rem; white-space:nowrap; }}
    .facts .k {{ color:var(--soft); font-size:.7rem; letter-spacing:.09em; text-transform:uppercase; font-weight:600; }}
    .facts .v {{ font-weight:700; }}
    .facts .v.time {{ font-weight:600; color:var(--soft); }}
    .note {{ border-left:3px solid var(--clay); background:var(--card); padding:1.1rem 1.35rem; border-radius:0 12px 12px 0; margin:0 0 1rem; }}
    .note h2 {{ font-size:1.08rem; font-weight:700; margin:0 0 .45rem; }}
    .note p {{ margin:.3rem 0; }} .note .ask {{ color:var(--clay); font-size:.92rem; }}
    .note.ok {{ border-left-color:var(--sage); }} .note.ok h2 {{ color:var(--ink); }}
    .produced {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.95rem 1.2rem; margin:0 0 1rem; font-size:1rem; }}
    .produced b {{ color:var(--sage); }}
    h2.sec {{ font-size:.74rem; letter-spacing:.14em; text-transform:uppercase; color:var(--soft); font-weight:700; margin:2.6rem 0 1.1rem; }}
    h3.subsec {{ font-size:.96rem; font-weight:700; margin:1.4rem 0 .3rem; }}
    .teaser {{ margin:.6rem 0 .4rem; }}
    .teaser .lead {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.8rem 1.1rem; margin:.2rem 0 .4rem; }}
    .teaser .lead .q {{ font-weight:700; }}
    .meta.red {{ color:#b42318; }} .meta.amber {{ color:var(--clay); }} .meta.muted {{ color:var(--soft); }}
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
    .bjourney {{ margin:.4rem 0 .6rem; }}
    .aud {{ border:0; padding:0; margin:.4rem 0 0; display:flex; flex-wrap:wrap; align-items:center; gap:.3rem; }}
    .aud-legend {{ font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; color:var(--soft); font-weight:700; margin-right:.55rem; }}
    .aud input {{ position:absolute; opacity:0; width:1px; height:1px; }}
    .aud input + label {{ font-size:.8rem; font-weight:600; color:var(--soft); background:var(--chip); border-radius:999px; padding:.22rem .7rem; cursor:pointer; }}
    .aud input:checked + label {{ background:var(--clay); color:var(--paper); }}
    .aud input:focus-visible + label {{ outline:3px solid var(--focus); outline-offset:2px; }}
    .note-college, .note-hobbyist {{ display:none; color:var(--soft); }}
    .bjourney:has(#aud-college:checked) .note-college {{ display:inline; }}
    .bjourney:has(#aud-hobbyist:checked) .note-hobbyist {{ display:inline; }}
    .journey-body {{ margin-top:.9rem; }}
    .asm {{ list-style:none; padding:0; margin:.3rem 0 1rem; display:grid; gap:.5rem; }}
    .asm li {{ border:1px solid var(--line); border-left-width:3px; border-radius:10px; padding:.6rem .85rem; background:var(--card); }}
    .asm li.broken {{ border-left-color:#b42318; }}
    .asm li.holding {{ border-left-color:var(--gold); }}
    .asm li.validated {{ border-left-color:var(--sage); }}
    .asm .stt {{ font-size:.68rem; letter-spacing:.04em; text-transform:uppercase; font-weight:700; margin-left:.4rem; }}
    .asm .broken-t {{ color:#b42318; }} .asm .holding-t {{ color:var(--gold); }} .asm .validated-t {{ color:var(--sage); }}
    .asm .lb {{ font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; color:var(--clay); margin-left:.4rem; }}
    .asm .toward {{ color:var(--soft); font-size:.85rem; display:block; margin-top:.2rem; }}
    .oq {{ margin:.2rem 0 1rem 1.1rem; color:var(--soft); font-size:.9rem; }}
    footer {{ margin-top:2.8rem; color:var(--soft); font-size:.8rem; letter-spacing:.03em; }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="wrap">
    <p class="kicker"><span class="dot"></span>The goal journey · {escape(snapshot.status)}</p>
    <h1 class="title">{escape(snapshot.objective)}</h1>
    {full_goal}
    <p class="journey">From first intent to finished proof — every step, decision, and check along the way.</p>
    <p class="orient">Read-only snapshot — the agent updates this as it works. Sections below expand for detail.</p>

    <div class="meter"><span class="big">{accepted} of {total}</span><span class="small">steps accepted · {escape(brief.progress)}</span></div>
    <div class="rule" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100" aria-label="{accepted} of {total} steps accepted"><i style="width:{pct}%"></i></div>
    <p class="facts">
      <span class="fact"><span class="k">Waiting on</span> <span class="v">{escape(_waiting_label(brief.waiting_on))}</span></span>
      <span class="fact"><span class="k">Proof</span> <span class="v">{proof}/{total} steps</span></span>
      <span class="fact"><span class="k">Updated</span> <span class="v time">{escape(_friendly_timestamp(snapshot.last_updated))}</span></span>
    </p>

    <main id="main" tabindex="-1">
    {status_banner}
    {produced}

    <h2 class="sec">What happened</h2>
    <h3 class="subsec">The steps</h3>
    <ul class="steps">{steps}</ul>
    {journey_section}
    {decisions_teaser}

    <h2 class="sec">Checks &amp; references</h2>
    {issues_section}
    <details><summary>Proof &amp; evidence<span class="meta">{proof} of {total} recorded</span></summary>
      <div class="body">{evidence}</div>
    </details>
    {lineage_section}
    {architecture_section}
    {sources_section}
    <details><summary>Technical details</summary>
      <div class="body">
        <p>Goal ID: <code>{escape(snapshot.goal_id)}</code> · Event offset: <code>{snapshot.event_count}</code> ·
        Source commit: <code>{escape(source_commit(Path(snapshot.topology.worktree_path)))}</code></p>
        <p>Read-only, generated by Goals from sanitized snapshot state.</p>
      </div>
    </details>
    </main>
    <footer>Powered by <a href="https://github.com/ShivamGupta42/goals" target="_blank" rel="noopener">Goals</a> · read-only</footer>
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


# Objectives longer than this (roughly two lines at the title size) get a
# "Read the full goal" expander; the clamped <h1> still carries the full text
# for screen readers.
_TITLE_CLAMP_CHARS = 90


def _full_goal_html(objective: str) -> str:
    """Reveal the complete objective below the clamped title, when it's long."""
    if len(objective) <= _TITLE_CLAMP_CHARS:
        return ""
    return (
        '<details class="full-goal"><summary>Read the full goal</summary>'
        f"<p>{escape(objective)}</p></details>"
    )


# One plain-language sentence per goal status — what's happening and whether the
# viewer needs to act. {step} is filled with the current step when active.
_STATUS_MESSAGES = {
    "active": "The agent is working{step}. Nothing is needed from you right now.",
    "complete": "This goal is complete. See what was produced below.",
    "blocked": "Blocked — see Issues below for what's in the way.",
    "paused": "Paused — resume in your agent when you're ready.",
    "failed": "This goal stopped before finishing — see Issues below.",
}


def _status_banner_html(snapshot: GoalSnapshot, brief, checkpoint, open_questions: list[str]) -> str:
    """Always render one status sentence at the top.

    If the user needs to act, the amber "Waiting on you" note wins. Otherwise a
    calm banner states what's happening, keyed on the goal status.
    """
    needs_you = _needs_you_html(brief, open_questions)
    if needs_you:
        return needs_you
    status = str(snapshot.status)
    step = ""
    if status == "active" and checkpoint and checkpoint.phase_title:
        step = f" on {escape(checkpoint.phase_title)}"
    message = _STATUS_MESSAGES.get(status, "Tracking progress.").format(step=step)
    return f'<div class="note ok"><h2>Status</h2><p>{message}</p></div>'


# what_changed fallbacks that carry no real deliverable — don't surface these.
_NO_DELIVERABLE = {
    "No current phase is selected.",
    "No change summary has been recorded yet.",
}


def _produced_html(checkpoint) -> str:
    """Surface the deliverable up front, when one has actually been recorded."""
    if not checkpoint:
        return ""
    what = (checkpoint.what_changed or "").strip()
    if not what or what in _NO_DELIVERABLE:
        return ""
    return f'<p class="produced"><b>What was produced</b> — {escape(what)}</p>'


def _friendly_timestamp(iso: str) -> str:
    """Turn an ISO timestamp into e.g. `Jun 14, 2026 · 5:40 PM UTC`.

    Only states what the value actually carries: a naive timestamp renders
    without a zone label (we don't assert a zone it never had) and a date-only
    string renders without a time. Falls back to the raw string if it can't be
    parsed, so a malformed value never breaks the page.
    """
    try:
        moment = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso
    date_part = f"{moment:%b} {moment.day}, {moment.year}"
    if "T" not in iso and ":" not in iso:  # date-only input — no time to show
        return date_part
    hour = moment.hour % 12 or 12
    meridiem = "AM" if moment.hour < 12 else "PM"
    zone = moment.tzname() if moment.tzinfo else ""
    suffix = f" {zone}" if zone else ""
    return f"{date_part} · {hour}:{moment.minute:02d} {meridiem}{suffix}"


def _waiting_label(value: str) -> str:
    # Answer *whose turn* it is; the goal status (eyebrow + banner) already says
    # whether the agent is working, paused, or done — don't restate it here and
    # risk contradicting it (e.g. "Agent (working)" on a complete goal).
    return {
        "you": "You",
        "agent": "Agent",
        "no one": "No one",
    }.get(str(value), str(value))


def _journey_html(snapshot: GoalSnapshot) -> str:
    """The building journey — how the agent broke the problem down and what it assumed.

    Renders nothing until the agent has recorded a breakdown or an assumption, so a
    goal with no Assess trace looks exactly as before. The audience toggle is pure
    CSS: a `role="radiogroup"` of three radios (high-school checked), and the
    `.bjourney:has(#aud-*:checked) .note-*` rules reveal the richer framings — no JS,
    and keyboard/screen-reader operable as a named native radio group.
    """
    if not snapshot.breakdowns and not snapshot.assumptions:
        return ""
    body = _breakdowns_html(snapshot) + _assumptions_html(snapshot)
    return (
        '<section class="bjourney" aria-label="The building journey">'
        '<h3 class="subsec">The building journey</h3>'
        '<div class="aud" role="radiogroup" aria-label="Explain it like">'
        '<span class="aud-legend" aria-hidden="true">Explain it like</span>'
        '<input type="radio" id="aud-hs" name="aud" checked>'
        '<label for="aud-hs">High school</label>'
        '<input type="radio" id="aud-college" name="aud">'
        '<label for="aud-college">College</label>'
        '<input type="radio" id="aud-hobbyist" name="aud">'
        '<label for="aud-hobbyist">Hobbyist</label>'
        "</div>"
        f'<div class="journey-body">{body}</div>'
        "</section>"
    )


def _breakdowns_html(snapshot: GoalSnapshot) -> str:
    if not snapshot.breakdowns:
        return ""
    blocks = []
    for breakdown in snapshot.breakdowns:
        scope = (
            f' <span class="meta muted">{escape(breakdown.phase_id)}</span>'
            if breakdown.phase_id
            else ""
        )
        pause = (
            f'<p class="body">Paused to check: {escape(breakdown.pause_note)}</p>'
            if breakdown.pause_note
            else ""
        )
        subs = []
        questions: list[str] = []
        for sub in breakdown.subproblems:
            tasks = (
                f'<br><span class="d">Tasks: {escape(", ".join(sub.tasks))}</span>'
                if sub.tasks
                else ""
            )
            subs.append(
                f'<li><span class="t">{escape(sub.statement)}</span>'
                f"{_audience_notes_html(sub.audience_notes)}{tasks}</li>"
            )
            questions.extend(sub.open_questions)
        subs_html = f'<ul class="kv">{"".join(subs)}</ul>' if subs else ""
        oq_html = (
            '<p class="d">Open questions</p><ul class="oq">'
            + "".join(f"<li>{escape(q)}</li>" for q in questions)
            + "</ul>"
            if questions
            else ""
        )
        system = (
            f'<p class="d">What keeps feeding this: {escape(breakdown.system_view)}</p>'
            if breakdown.system_view
            else ""
        )
        blocks.append(
            f'<h4 class="subsec">{escape(breakdown.problem)}'
            f"{_audience_notes_html(breakdown.audience_notes)}{scope}</h4>"
            f"{pause}{subs_html}{oq_html}{system}"
        )
    return "".join(blocks)


def _audience_notes_html(notes: dict[str, str]) -> str:
    """Reveal-on-toggle college/hobbyist framing for a breakdown problem or sub-problem.

    Mirrors the assumption notes: hidden by default, revealed by the same
    `.bjourney:has(#aud-*:checked)` CSS, so the audience toggle now simplifies the
    whole journey — not just the assumptions.
    """
    college = notes.get("college", "")
    hobbyist = notes.get("hobbyist", "")
    out = ""
    if college:
        out += f' <span class="note-college">{escape(college)}</span>'
    if hobbyist:
        out += f' <span class="note-hobbyist">{escape(hobbyist)}</span>'
    return out


def _assumptions_html(snapshot: GoalSnapshot) -> str:
    if not snapshot.assumptions:
        return ""
    items = []
    for assumption in sort_assumptions(snapshot.assumptions):
        status = assumption.status
        lb = '<span class="lb">load-bearing</span>' if assumption.depends_on else ""
        college = assumption.audience_notes.get("college", "")
        hobbyist = assumption.audience_notes.get("hobbyist", "")
        college_html = (
            f' <span class="note-college">{escape(college)}</span>' if college else ""
        )
        hobbyist_html = (
            f' <span class="note-hobbyist">{escape(hobbyist)}</span>' if hobbyist else ""
        )
        toward = (
            f'<span class="toward">toward: {escape(assumption.toward)}</span>'
            if assumption.toward
            else ""
        )
        items.append(
            f'<li class="{escape(status)}"><span>{escape(assumption.statement)}</span>'
            f"{college_html}{hobbyist_html}"
            f'<span class="stt {escape(status)}-t">{escape(status)}</span>{lb}'
            f"{toward}</li>"
        )
    return '<p class="d">What the agent assumed</p><ul class="asm">' + "".join(items) + "</ul>"


def _decisions_teaser_html(snapshot: GoalSnapshot) -> str:
    """Tier-2 decision log: latest call inline, full log behind expand.

    Hidden entirely when no judgements have been recorded.
    """
    if not snapshot.judgements:
        return ""
    latest = snapshot.judgements[-1]
    count = len(snapshot.judgements)
    reversible = "reversible" if latest.reversible else "irreversible"
    return (
        '<div class="teaser">'
        f'<h3 class="subsec">Decisions <span class="meta muted">{count} recorded</span></h3>'
        '<div class="lead">'
        f'<span class="q">{escape(latest.question)}</span><br>'
        f'<span class="d">Chose: {escape(latest.choice)}'
        f'<span class="chip">{escape(latest.decided_by)}</span>'
        f'<span class="chip">{reversible}</span></span></div>'
        f'<details><summary>See all {count} decisions</summary>'
        f'<div class="body">{_decisions_log_html(snapshot)}</div></details>'
        "</div>"
    )


def _issues_section_html(report) -> str:
    """Collapsible Issues section, auto-opened and red when something blocks.

    Hidden when there are no issues — the top banner already signals health.
    """
    if not report.issues:
        return ""
    has_blocking = any(issue.severity == "p0" for issue in report.issues)
    has_important = any(issue.severity == "p1" for issue in report.issues)
    tone = "red" if has_blocking else ("amber" if has_important else "muted")
    open_attr = " open" if has_blocking else ""
    return (
        f"<details{open_attr}><summary>Issues"
        f'<span class="meta {tone}">{_issues_meta(report)}</span></summary>'
        f'<div class="body">{_issues_html(report)}</div></details>'
    )


def _architecture_section_html(
    snapshot: GoalSnapshot, architecture, architecture_path, has_recorded: bool
) -> str:
    """Show the architecture map only when an agent recorded a real one."""
    if not has_recorded:
        return ""
    return (
        f'<details><summary>Architecture map<span class="meta">{_arch_meta(architecture)}</span>'
        "</summary>"
        f'<div class="body">{_architecture_detail_html(snapshot, architecture, architecture_path)}</div>'
        "</details>"
    )


def _sources_section_html(snapshot: GoalSnapshot) -> str:
    """Show Sources only when sources or claims exist."""
    if not snapshot.sources and not snapshot.source_claims:
        return ""
    return (
        f'<details><summary>Sources<span class="meta">{_sources_meta(snapshot)}</span></summary>'
        f'<div class="body">{_sources_html(snapshot)}</div></details>'
    )


def _lineage_section_html(snapshot: GoalSnapshot, events: list[Event]) -> str:
    if not events:
        return ""
    phase_id = snapshot.current_phase or _latest_phase_id(events)
    if not phase_id:
        return ""
    try:
        lineage = build_phase_lineage(events, phase_id)
    except Exception:  # noqa: BLE001
        return ""
    items = []
    latest_chain = lineage.chains[-1] if lineage.chains else []
    for item in latest_chain:
        phase = f" · {escape(item.phase_id)}" if item.phase_id else ""
        items.append(
            f'<li><span class="t">{escape(item.event_type)}{phase}</span>'
            f'<br><span class="d"><code>{escape(item.event_id)}</code> · '
            f'{escape(item.summary)}</span></li>'
        )
    if not items:
        return ""
    meta = f"{len(latest_chain)} event chain"
    return (
        f'<details><summary>Lineage<span class="meta">{escape(meta)}</span></summary>'
        '<div class="body"><p>Latest causal chain for the current phase.</p>'
        f'<ul class="kv">{"".join(items)}</ul></div></details>'
    )


def _latest_phase_id(events: list[Event]) -> str:
    for event in reversed(events):
        phase_id = event.payload.get("phase_id")
        if isinstance(phase_id, str):
            return phase_id
    return ""


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
        # Skip self-loops: a node pointing at itself would keep relaxing its own
        # layer on every pass, pushing it off the canvas.
        if edge.from_node in ids and edge.to_node in ids and edge.from_node != edge.to_node:
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
    # Clamp the column count so a cyclic graph (where relaxation never settles)
    # still lays out in a bounded, readable width instead of one column per node.
    max_col = min(len(nodes), 5)
    columns: dict[int, list] = {}
    for node in nodes:
        columns.setdefault(min(layer[node.node_id], max_col - 1), []).append(node)

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
        if (
            edge.from_node in position
            and edge.to_node in position
            and edge.from_node != edge.to_node
        ):
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


def _issues_meta(report) -> str:
    return "clear" if not report.issues else f"{len(report.issues)} open"


def _sources_meta(snapshot: GoalSnapshot) -> str:
    count = len(snapshot.sources)
    return "none yet" if not count else f"{count} source(s)"
