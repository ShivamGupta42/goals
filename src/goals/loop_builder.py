"""Visual goal-loop builder.

A terminal-first, text-based builder that lets a user compose a goal "loop":
ordered phases (blocks) with acceptance criteria, termination conditions, and
attached skills discovered live from the agent skill dirs.

Design philosophy (see docs/VISUAL_BUILDER_GOAL.md):

* **One source of truth.** :class:`LoopDesign` is the richer design artifact.
  It *compiles down* to the existing portable goal spec (``goal-state.json`` +
  ``GOAL.md``) by reusing :mod:`goals.portability` — it never reimplements it.
  The standalone HTML is rendered from the same design, so the two surfaces
  (portable spec + HTML) can never drift.
* **Skills discovered live, never registered.** A phase stores only skill *name*
  references. Which agent has each skill — and whether it is missing from
  ``~/.agents/skills`` — is resolved at render/check time via
  :func:`goals.skill_discovery.discover_skills`, so the durable design stays
  environment-independent and committable.
* **Thin.** No server, no curses, no new runtime dependency. The interactive
  builder is a line REPL over a pure command core (:func:`apply_command`), which
  makes every path testable and lets a script reproduce a loop deterministically.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from goals.git_ops import slugify
from goals.models import GoalSnapshot, Phase, PhaseProtocol, WorktreeLease, utc_now
from goals.portability import build_portable_state, render_goal_markdown
from goals.skill_discovery import DiscoveredSkill, discover_skills
from goals.storage import GoalsError, atomic_write_text

#: Bumped independently of the portable spec: this is the builder's own design
#: artifact, not the vendor-neutral goal contract.
LOOP_DESIGN_VERSION = 1

_TRAILING_NUM_RE = re.compile(r"(\d+)$")


# --------------------------------------------------------------------------- #
# Design model (the single source of truth)
# --------------------------------------------------------------------------- #
class LoopPhase(BaseModel):
    """One block in the loop. Skills are stored as name references only."""

    model_config = ConfigDict(extra="forbid")

    phase_id: str
    title: str
    goal: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    termination_conditions: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    validation_profiles: list[str] = Field(default_factory=list)


class LoopDesign(BaseModel):
    """A composed goal loop. Compiles to the portable spec; renders to HTML."""

    model_config = ConfigDict(extra="forbid")

    builder_version: int = LOOP_DESIGN_VERSION
    objective: str = ""
    why: str = ""
    definition_of_done: list[str] = Field(default_factory=list)
    phases: list[LoopPhase] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
DESIGN_FILENAME = "loop-design.json"
HTML_FILENAME = "loop.html"
STATE_FILENAME = "goal-state.json"
MARKDOWN_FILENAME = "GOAL.md"


class LoopSaveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design_path: str
    state_path: str
    markdown_path: str
    html_path: str


def save_design(
    design: LoopDesign,
    out_dir: Path,
    *,
    skills: list[DiscoveredSkill] | None = None,
) -> LoopSaveResult:
    """Write the design artifact, the portable spec pair, and the HTML export.

    All four derive from ``design`` — the portable spec via
    :mod:`goals.portability`, the HTML via :func:`render_loop_html` — so they are
    always consistent with each other.
    """
    discovered = skills if skills is not None else discover_skills()
    out_dir.mkdir(parents=True, exist_ok=True)
    design_path = out_dir / DESIGN_FILENAME
    state_path = out_dir / STATE_FILENAME
    markdown_path = out_dir / MARKDOWN_FILENAME
    html_path = out_dir / HTML_FILENAME

    snapshot = to_snapshot(design)
    atomic_write_text(design_path, design.model_dump_json(indent=2) + "\n")
    atomic_write_text(
        state_path,
        json.dumps(build_portable_state(snapshot), indent=2, ensure_ascii=False) + "\n",
    )
    atomic_write_text(markdown_path, render_goal_markdown(snapshot))
    atomic_write_text(html_path, render_loop_html(design, skills=discovered))
    return LoopSaveResult(
        design_path=str(design_path),
        state_path=str(state_path),
        markdown_path=str(markdown_path),
        html_path=str(html_path),
    )


def load_design(path: Path) -> LoopDesign:
    """Load a saved design. ``path`` may be the file or its containing dir."""
    if path.is_dir():
        path = path / DESIGN_FILENAME
    if not path.exists():
        raise GoalsError(f"No loop design found at {path}.")
    try:
        return LoopDesign.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GoalsError(f"Invalid loop design at {path}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Portable-spec projection (reuse, never reinvent, portability.py)
# --------------------------------------------------------------------------- #
def to_snapshot(design: LoopDesign) -> GoalSnapshot:
    """Project the design into a valid :class:`GoalSnapshot`.

    Termination conditions and attached skill references stay as structured
    protocol metadata. The topology is a synthetic placeholder: the portable spec
    is path-sanitized and only reads ``topology.branch``.
    """
    slug = slugify(design.objective) if design.objective else "loop"
    ids = [phase.phase_id for phase in design.phases]
    duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
    if duplicates:
        # A hand-edited loop-design.json could collide ids; the portable spec
        # treats phase_id as identity, so fail loud instead of emitting a spec
        # where two phases share an id.
        raise GoalsError(f"Duplicate phase ids in loop design: {', '.join(duplicates)}")
    phases = [
        Phase(
            phase_id=phase.phase_id,
            title=phase.title,
            goal=phase.goal,
            acceptance_criteria=list(phase.acceptance_criteria),
            protocol=PhaseProtocol(
                termination_conditions=list(phase.termination_conditions),
                skills=list(phase.skills),
                validation_profiles=list(phase.validation_profiles),
            ),
        )
        for phase in design.phases
    ]
    return GoalSnapshot(
        goal_id=slug,
        objective=design.objective or "Untitled loop",
        why=design.why,
        definition_of_done=list(design.definition_of_done),
        topology=WorktreeLease(
            base_repo=".",
            base_branch="main",
            worktree_path=".",
            branch=f"loop/{slug}",
        ),
        phases=phases,
        current_phase=phases[0].phase_id if phases else None,
        last_updated=utc_now(),
    )


def to_portable_state(design: LoopDesign) -> dict:
    """The portable goal-state dict for this design (via portability.py)."""
    return build_portable_state(to_snapshot(design))


# --------------------------------------------------------------------------- #
# Interactive builder — pure command core
# --------------------------------------------------------------------------- #
@dataclass
class BuilderSession:
    """Mutable builder state. ``skills`` is injected so discovery is testable."""

    design: LoopDesign
    out_dir: Path
    skills: list[DiscoveredSkill] = field(default_factory=list)
    selected: str | None = None


@dataclass
class BuilderResponse:
    message: str
    exit: bool = False


_HELP = """Commands:
  objective <text>          set the loop objective
  why <text>                set why this loop matters
  dod <text>                add a definition-of-done line
  add <title>[ :: <goal>]   add a phase (becomes the selected phase)
  select <id>               select a phase to edit
  title <text>              rename the selected phase
  goal <text>               set the selected phase's goal
  accept <text>             add an acceptance criterion to the selected phase
  terminate <text>          add a termination condition to the selected phase
  profile <name>            attach a validation profile to the selected phase
  skills [query]            list skills discovered live (optionally filtered)
  attach <skill-name>       attach a discovered skill to the selected phase
  move <id> up|down         reorder a phase
  delete <id>               delete a phase
  show                      print the current loop
  check                     lint the loop for issues
  save [dir]                write the design, portable spec, and HTML export
  help                      show this help
  quit                      exit the builder""".rstrip()


def new_session(out_dir: Path, *, skills: list[DiscoveredSkill] | None = None) -> BuilderSession:
    return BuilderSession(
        design=LoopDesign(),
        out_dir=out_dir,
        skills=skills if skills is not None else discover_skills(),
    )


def apply_command(session: BuilderSession, line: str) -> BuilderResponse:
    """Apply one builder command to the session and return a response.

    Pure with respect to the session except for ``save`` (writes files) — every
    structural mutation is in-memory, which is what makes the builder scriptable
    and fully testable.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return BuilderResponse("")
    command, _, rest = line.partition(" ")
    command = command.lower()
    rest = rest.strip()
    handler = _COMMANDS.get(command)
    if handler is None:
        return BuilderResponse(f"Unknown command: {command}. Type 'help'.")
    return handler(session, rest)


def _cmd_objective(session: BuilderSession, rest: str) -> BuilderResponse:
    if not rest:
        return BuilderResponse("Usage: objective <text>")
    session.design.objective = rest
    return BuilderResponse(f"Objective: {rest}")


def _cmd_why(session: BuilderSession, rest: str) -> BuilderResponse:
    session.design.why = rest
    return BuilderResponse(f"Why: {rest}" if rest else "Cleared why.")


def _cmd_dod(session: BuilderSession, rest: str) -> BuilderResponse:
    if not rest:
        return BuilderResponse("Usage: dod <text>")
    session.design.definition_of_done.append(rest)
    return BuilderResponse(f"Added definition of done: {rest}")


def _cmd_add(session: BuilderSession, rest: str) -> BuilderResponse:
    if not rest:
        return BuilderResponse("Usage: add <title>[ :: <goal>]")
    title, _, goal = rest.partition("::")
    title = title.strip()
    if not title:
        return BuilderResponse("A phase needs a title. Usage: add <title>[ :: <goal>]")
    phase = LoopPhase(
        phase_id=_next_phase_id(session.design),
        title=title,
        goal=goal.strip(),
    )
    session.design.phases.append(phase)
    session.selected = phase.phase_id
    return BuilderResponse(f"Added {phase.phase_id}: {phase.title} (selected)")


def _cmd_select(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _find(session.design, rest)
    if phase is None:
        return BuilderResponse(f"No phase with id {rest!r}.")
    session.selected = phase.phase_id
    return BuilderResponse(f"Selected {phase.phase_id}: {phase.title}")


def _cmd_title(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _selected_or_none(session)
    if phase is None:
        return BuilderResponse("Select a phase first (select <id>).")
    if not rest:
        return BuilderResponse("Usage: title <text>")
    phase.title = rest
    return BuilderResponse(f"{phase.phase_id} title: {rest}")


def _cmd_goal(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _selected_or_none(session)
    if phase is None:
        return BuilderResponse("Select a phase first (select <id>).")
    phase.goal = rest
    return BuilderResponse(f"{phase.phase_id} goal: {rest}")


def _cmd_accept(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _selected_or_none(session)
    if phase is None:
        return BuilderResponse("Select a phase first (select <id>).")
    if not rest:
        return BuilderResponse("Usage: accept <text>")
    phase.acceptance_criteria.append(rest)
    return BuilderResponse(f"{phase.phase_id} acceptance += {rest}")


def _cmd_terminate(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _selected_or_none(session)
    if phase is None:
        return BuilderResponse("Select a phase first (select <id>).")
    if not rest:
        return BuilderResponse("Usage: terminate <text>")
    phase.termination_conditions.append(rest)
    return BuilderResponse(f"{phase.phase_id} termination += {rest}")


def _cmd_profile(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _selected_or_none(session)
    if phase is None:
        return BuilderResponse("Select a phase first (select <id>).")
    if not rest:
        return BuilderResponse("Usage: profile <name>")
    if rest in phase.validation_profiles:
        return BuilderResponse(f"{rest} is already attached to {phase.phase_id}.")
    phase.validation_profiles.append(rest)
    return BuilderResponse(f"{phase.phase_id} validation profile += {rest}")


def _cmd_skills(session: BuilderSession, rest: str) -> BuilderResponse:
    matches = _search_skills(session.skills, rest)
    if not matches:
        scope = f" matching {rest!r}" if rest else ""
        return BuilderResponse(f"No skills discovered{scope}.")
    lines = [_skill_line(skill) for skill in matches]
    return BuilderResponse("\n".join(lines))


def _cmd_attach(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _selected_or_none(session)
    if phase is None:
        return BuilderResponse("Select a phase first (select <id>).")
    if not rest:
        return BuilderResponse("Usage: attach <skill-name>")
    if rest in phase.skills:
        return BuilderResponse(f"{rest} is already attached to {phase.phase_id}.")
    skill = _find_skill(session.skills, rest)
    phase.skills.append(rest)
    if skill is None:
        return BuilderResponse(
            f"Attached {rest} to {phase.phase_id}. "
            f"Warning: no skill named {rest!r} was discovered in your agent dirs."
        )
    note = _install_hint(skill)
    message = f"Attached {rest} to {phase.phase_id} [{_agents_label(skill)}]."
    return BuilderResponse(f"{message}\n{note}" if note else message)


def _cmd_move(session: BuilderSession, rest: str) -> BuilderResponse:
    phase_id, _, direction = rest.partition(" ")
    direction = direction.strip().lower()
    if direction not in {"up", "down"}:
        return BuilderResponse("Usage: move <id> up|down")
    phases = session.design.phases
    index = next((i for i, p in enumerate(phases) if p.phase_id == phase_id), None)
    if index is None:
        return BuilderResponse(f"No phase with id {phase_id!r}.")
    target = index - 1 if direction == "up" else index + 1
    if target < 0 or target >= len(phases):
        return BuilderResponse(f"{phase_id} is already at the {direction!r} edge.")
    phases[index], phases[target] = phases[target], phases[index]
    return BuilderResponse(f"Moved {phase_id} {direction}.")


def _cmd_delete(session: BuilderSession, rest: str) -> BuilderResponse:
    phase = _find(session.design, rest)
    if phase is None:
        return BuilderResponse(f"No phase with id {rest!r}.")
    session.design.phases = [p for p in session.design.phases if p.phase_id != phase.phase_id]
    if session.selected == phase.phase_id:
        session.selected = None
    return BuilderResponse(f"Deleted {phase.phase_id}.")


def _cmd_show(session: BuilderSession, rest: str) -> BuilderResponse:
    return BuilderResponse(render_loop_text(session.design, selected=session.selected))


def _cmd_check(session: BuilderSession, rest: str) -> BuilderResponse:
    # Imported lazily: the linter lands in Phase 2; keep Phase 1 self-contained.
    try:
        from goals.loop_check import check_loop, render_loop_check_report
    except ImportError:  # pragma: no cover - until Phase 2 lands
        return BuilderResponse("Loop checking is not available yet.")
    report = check_loop(session.design, skills=session.skills)
    return BuilderResponse(render_loop_check_report(report))


def _cmd_save(session: BuilderSession, rest: str) -> BuilderResponse:
    out_dir = Path(rest).expanduser() if rest else session.out_dir
    result = save_design(session.design, out_dir, skills=session.skills)
    return BuilderResponse(
        "Saved:\n"
        f"- design:   {result.design_path}\n"
        f"- spec:     {result.state_path}\n"
        f"- markdown: {result.markdown_path}\n"
        f"- html:     {result.html_path}"
    )


def _cmd_help(session: BuilderSession, rest: str) -> BuilderResponse:
    return BuilderResponse(_HELP)


def _cmd_quit(session: BuilderSession, rest: str) -> BuilderResponse:
    return BuilderResponse("Bye.", exit=True)


_COMMANDS = {
    "objective": _cmd_objective,
    "why": _cmd_why,
    "dod": _cmd_dod,
    "add": _cmd_add,
    "select": _cmd_select,
    "title": _cmd_title,
    "goal": _cmd_goal,
    "accept": _cmd_accept,
    "terminate": _cmd_terminate,
    "profile": _cmd_profile,
    "skills": _cmd_skills,
    "attach": _cmd_attach,
    "move": _cmd_move,
    "delete": _cmd_delete,
    "show": _cmd_show,
    "check": _cmd_check,
    "save": _cmd_save,
    "help": _cmd_help,
    "quit": _cmd_quit,
    "exit": _cmd_quit,
}


# --------------------------------------------------------------------------- #
# Interactive loop (thin I/O shell over the pure core)
# --------------------------------------------------------------------------- #
def run_builder(session: BuilderSession, *, read=input, write=print, prompt: str = "loop> ") -> None:
    """Run the line REPL until the user quits or input is exhausted."""
    write("Goals loop builder. Type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            line = read(prompt)
        except EOFError:
            break
        response = apply_command(session, line)
        if response.message:
            write(response.message)
        if response.exit:
            break


def run_script(session: BuilderSession, commands: list[str], *, write=print) -> None:
    """Drive the builder from a list of commands (one per line)."""
    for line in commands:
        response = apply_command(session, line)
        if response.message:
            write(response.message)
        if response.exit:
            break


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_loop_text(design: LoopDesign, *, selected: str | None = None) -> str:
    lines = [f"Objective: {design.objective or '(none)'}"]
    if design.why:
        lines.append(f"Why: {design.why}")
    if design.definition_of_done:
        lines.append("Definition of done:")
        lines += [f"  - {item}" for item in design.definition_of_done]
    if not design.phases:
        lines.append("No phases yet. Add one with: add <title>")
        return "\n".join(lines)
    lines.append("Phases:")
    for phase in design.phases:
        marker = "*" if phase.phase_id == selected else " "
        lines.append(f" {marker}{phase.phase_id} {phase.title}")
        if phase.goal:
            lines.append(f"     goal: {phase.goal}")
        for criterion in phase.acceptance_criteria:
            lines.append(f"     accept: {criterion}")
        for cond in phase.termination_conditions:
            lines.append(f"     terminate: {cond}")
        for profile in phase.validation_profiles:
            lines.append(f"     profile: {profile}")
        for name in phase.skills:
            lines.append(f"     skill: {name}")
    return "\n".join(lines)


def render_loop_html(design: LoopDesign, *, skills: list[DiscoveredSkill] | None = None) -> str:
    """Render a standalone, server-free HTML visualization of the loop.

    Skill availability (and the Claude-only install hint) is resolved live from
    ``skills`` so the HTML reflects the environment it is exported in.
    """
    discovered = skills if skills is not None else discover_skills()
    by_name = {skill.name: skill for skill in discovered}
    objective = escape(design.objective or "Untitled loop")
    dod = "".join(f"<li>{escape(item)}</li>" for item in design.definition_of_done)
    # Arrows connect phases, so the first phase has none.
    phases_html = '<div class="arrow">&darr;</div>'.join(
        _phase_html(phase, by_name) for phase in design.phases
    )
    if not design.phases:
        phases_html = '<p class="empty">No phases yet.</p>'
    why_html = f'<p class="why">{escape(design.why)}</p>' if design.why else ""
    dod_html = f"<h2>Definition of Done</h2><ul>{dod}</ul>" if dod else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Goal Loop - {objective}</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 0;
           background: #f6f7f9; color: #1d2330; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }}
    h1 {{ font-size: 1.6rem; margin: 0 0 .25rem; }}
    .why {{ color: #555f72; margin-top: 0; }}
    .phase {{ background: #fff; border: 1px solid #e2e6ee; border-radius: 12px;
             padding: 1rem 1.25rem; margin: 1rem 0; }}
    .phase h3 {{ margin: 0 0 .5rem; }}
    .pill {{ display: inline-block; background: #eef1f7; border-radius: 999px;
            padding: .1rem .6rem; font-size: .78rem; margin-right: .35rem; }}
    .arrow {{ text-align: center; color: #97a0b3; font-size: 1.2rem; margin: -.4rem 0; }}
    .skill {{ border-left: 3px solid #6b8afd; padding: .15rem .6rem; margin: .3rem 0;
             background: #f4f7ff; border-radius: 4px; font-size: .9rem; }}
    .hint {{ color: #9a6a00; font-size: .82rem; }}
    .label {{ font-weight: 600; font-size: .8rem; color: #555f72;
             text-transform: uppercase; letter-spacing: .03em; }}
    ul {{ margin: .3rem 0 .6rem; }}
    .empty {{ color: #97a0b3; }}
  </style>
</head>
<body>
  <main>
    <h1>{objective}</h1>
    {why_html}
    {dod_html}
    <h2>Loop</h2>
    {phases_html}
  </main>
</body>
</html>
"""


def _phase_html(phase: LoopPhase, by_name: dict[str, DiscoveredSkill]) -> str:
    parts = [
        '<section class="phase">',
        f'<h3><span class="pill">{escape(phase.phase_id)}</span>{escape(phase.title)}</h3>',
    ]
    if phase.goal:
        parts.append(f"<p>{escape(phase.goal)}</p>")
    if phase.acceptance_criteria:
        items = "".join(f"<li>{escape(c)}</li>" for c in phase.acceptance_criteria)
        parts.append(f'<p class="label">Acceptance</p><ul>{items}</ul>')
    if phase.termination_conditions:
        items = "".join(f"<li>{escape(c)}</li>" for c in phase.termination_conditions)
        parts.append(f'<p class="label">Termination</p><ul>{items}</ul>')
    if phase.validation_profiles:
        items = "".join(f"<li>{escape(c)}</li>" for c in phase.validation_profiles)
        parts.append(f'<p class="label">Validation profiles</p><ul>{items}</ul>')
    if phase.skills:
        parts.append('<p class="label">Skills</p>')
        for name in phase.skills:
            parts.append(_attached_skill_html(name, by_name.get(name)))
    parts.append("</section>")
    return "".join(parts)


def _attached_skill_html(name: str, skill: DiscoveredSkill | None) -> str:
    if skill is None:
        return (
            f'<div class="skill">{escape(name)} '
            f'<span class="hint">(not found in your agent dirs)</span></div>'
        )
    agents = _agents_label(skill)
    body = f'<div class="skill"><strong>{escape(name)}</strong> '
    body += f'<span class="pill">{escape(agents)}</span>'
    if skill.description:
        body += f"<br>{escape(skill.description)}"
    hint = _install_hint(skill)
    if hint:
        body += f'<br><span class="hint">{escape(hint)}</span>'
    return body + "</div>"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _next_phase_id(design: LoopDesign) -> str:
    """Next ``P<n>`` id that does not collide with any existing phase id.

    Scans the trailing integer of every id (not just well-formed ``P<n>`` ones)
    so a hand-edited or custom id never makes the counter restart at ``P1`` and
    silently collide.
    """
    nums = [
        int(match.group(1))
        for phase in design.phases
        if (match := _TRAILING_NUM_RE.search(phase.phase_id))
    ]
    candidate = (max(nums) + 1) if nums else 1
    existing = {phase.phase_id for phase in design.phases}
    while f"P{candidate}" in existing:
        candidate += 1
    return f"P{candidate}"


def _find(design: LoopDesign, phase_id: str) -> LoopPhase | None:
    return next((p for p in design.phases if p.phase_id == phase_id), None)


def _selected_or_none(session: BuilderSession) -> LoopPhase | None:
    if session.selected is None:
        return None
    return _find(session.design, session.selected)


def _search_skills(skills: list[DiscoveredSkill], query: str) -> list[DiscoveredSkill]:
    if not query:
        return skills
    needle = query.lower()
    return [
        skill
        for skill in skills
        if needle in skill.name.lower() or needle in skill.description.lower()
    ]


def _find_skill(skills: list[DiscoveredSkill], name: str) -> DiscoveredSkill | None:
    return next((skill for skill in skills if skill.name == name), None)


def _agents_label(skill: DiscoveredSkill) -> str:
    return ", ".join(skill.agents) if skill.agents else "bundled (not installed)"


def _install_hint(skill: DiscoveredSkill) -> str:
    """Suggest installing into ~/.agents/skills when a skill is Claude-only.

    Keeps the loop runnable under both Claude and Codex. Uses the ``~``-relative
    form (not the expanded absolute home path) so the hint is safe to embed in
    the committable, path-free ``.goals/loop.html`` export.
    """
    if "claude" in skill.agents and "codex" not in skill.agents:
        return (
            f"Suggestion: install {skill.name} into ~/.agents/skills so the loop "
            f"runs under Codex too (`goals skills install --target codex` for "
            "bundled skills, or copy the skill dir)."
        )
    return ""


def _skill_line(skill: DiscoveredSkill) -> str:
    description = skill.description
    if len(description) > 80:
        description = description[:79].rstrip() + "…"
    return f"- {skill.name} [{_agents_label(skill)}] — {description}"
