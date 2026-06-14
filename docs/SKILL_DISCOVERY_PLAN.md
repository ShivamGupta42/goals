# Plan — Unify Skill Discovery (retire the static catalog)

**Problem.** `registries/skills.yml` + `plugins.yml` + `goals ecosystem
recommend/merge` are a hand-curated catalog of vendor capabilities baked into a
vendor-neutral tool. It rots (knows ~6 generic entries; the user has 100+ skills
in `~/.claude/skills`, 8 in `~/.codex/skills`), it duplicates the agents' own
skill dirs, and it lists the repo's *own* commands as "skills." It is also
**already broken in real installs**: `ecosystem.py` resolves registries via
`Path(__file__).parents[2]/registries`, a path that does not exist after
`uv tool install`, so `ecosystem recommend` silently returns nothing for any
wheel-installed user.

**Resolution.** One discovery mechanism: live-scan `SKILL.md` files. Ship goals'
own capabilities as real skills that load from the repo by default. Retire the
catalog — *after* the replacement is green.

**Sequencing principle:** additive-first, delete-last. `main` stays shippable at
every phase; a failed deletion never strands us without `decision-explainer`.

**Scope split:**
- Native, preserve as bundled skills → `decision-explainer`
  (`goals decision brief` / `decision explain`), `architecture-map`
  (`goals architecture show`).
- Dead/external, drop → `safety-review` (`goals safety-check` does not exist),
  `code-review`, `comprehensive-testing`, `docs` (external/generic; live-scan
  finds the real ones).
- **Refactor, NOT untouched** → `permission_policy.py`. It currently imports
  `EcosystemRecommendation` and `goals permission check` depends on it. The
  *policy engine* (repo-local-safe / external / destructive, from
  `permissions.yml`) stays; its **input type** must be decoupled from the
  ecosystem model.
- **Keep** → `permissions.yml`, `gates.yml`, `profiles.yml`, `adapters.yml`,
  `agents.yml` (internal taxonomy/policy, not a vendor catalog).
- **Removed with no replacement (decided)** → `plugins.yml` + plugin
  recommendations. Plugins (github, browser, …) are not `SKILL.md` files, so live
  discovery has no equivalent. Dropped entirely — consistent with the
  anti-catalog stance.

---

## Review findings this revision fixes (evidence)
1. `permission_policy.py:9,100,121` couples the kept policy engine to
   `EcosystemRecommendation`; `cli.py:863 permission_check` calls
   `permission_report_for_recommendations`. → Phase 4 decouples first.
2. `pyproject.toml:22` packages only `src/goals`; repo-root `skills/` won't ship.
   The registries wheel bug proves the failure mode. → Phase 1 fixes packaging +
   a dual-path resolver.
3. `cli.py:1040` `goals decision explain` needs `--file` + active goal. → the
   bundled skill uses `goals decision brief` as entrypoint and states the
   goals-project requirement.
4. `mode_a.py:8,23,47,92,141` builds + renders `recommended_tools` and hard-codes
   `goals ecosystem merge` guidance in the handoff. → Phase 4 removes the field
   and updates the handoff prose.
5. `dashboard.py:60,139,166,443` renders a "Skills & Plugins" panel from the
   catalog. → Phase 4 repoints it to live discovery (`goals skills list` content).
6. `memory.py:371,389,407` routes the "ecosystem" friction area to
   `goals ecosystem recommend`. → Phase 4 repoints it to `goals skills`.
7. `ModeAPlan.recommended_tools` (`models.py:710`) is a **generated view**
   (`build_mode_a_plan`, workflows.py:76/84), never persisted → no
   backward-compat risk for existing goal files. Confirmed safe to delete.

---

## Phase 1 — Ship goals-native skills (additive)
Create bundled `SKILL.md` skills for the two surviving native capabilities. Each
body is prose instructing the agent which `goals` command to run and when; it is
not executable itself and assumes the goals CLI is on PATH.

- `decision-explainer/SKILL.md` — entrypoint `goals decision brief` (zero-arg,
  reads active goal); `goals decision explain --file <f> --level basic` for a
  specific decision file. State: "works inside a goals project (active goal
  worktree)."
- `architecture-map/SKILL.md` — `goals architecture show` / `brief`. Same
  goals-project caveat.
- Match the observed format: YAML frontmatter `name` + `description` (with a
  "Use when…" trigger phrase). **Identity = directory name** (canonical);
  frontmatter `name` is display only.
- **Packaging:** keep sources at repo-root `skills/` (copyable), and make them
  ship by adding a hatch `force-include` mapping `skills` →
  `goals/bundled_skills` so they land inside the installed package. Runtime reads
  them via a `bundled_skills_root()` helper that prefers the packaged location
  (`importlib.resources.files("goals") / "bundled_skills"`) and falls back to
  repo-root `skills/` for editable/dev installs. This avoids the registries
  wheel bug.

**Verify:** both `SKILL.md` parse; `goals decision brief` and
`goals architecture show` run; `uv build` produces a wheel whose contents include
`goals/bundled_skills/decision-explainer/SKILL.md` (inspect the wheel, don't
assume); `bundled_skills_root()` resolves in both editable and installed layouts.

## Phase 2 — Live discovery module
New `src/goals/skill_discovery.py`:
- `discover_skills()` scans three sources: `~/.claude/skills`, `~/.codex/skills`,
  and `bundled_skills_root()`.
- **Scan rules:** top-level only — `<source>/<dir>/SKILL.md`. Do **not** recurse
  into sub-skills (e.g. `product-design/skills/index/SKILL.md`). Skip non-dirs,
  dot-dirs (`.system`), and stray files (`README.md`).
- Parse frontmatter → `DiscoveredSkill(name, description, sources: list[str],
  agents: list[str], path)` (pydantic, `extra="forbid"`). `agents`/`sources`
  are **sorted lists** (deterministic for tests/rendering), never sets.
- **Dedupe by directory name.** When the same name appears in multiple sources,
  emit one entry whose `agents`/`sources` union all locations; the displayed
  description is taken by precedence `claude > codex > bundled`.
- Record agent availability factually. No nudge — the visual builder may later
  use this to flag loop portability; discovery only reports facts.
- Robustness: missing dir → skip; malformed/empty frontmatter or missing `name`
  → skip with no crash.

**Verify (tests):** temp-fixture scan covering claude-only, codex-only,
present-in-both (asserts union + precedence), and bundled-fallback. Assert
top-level-only (a nested sub-skill is ignored), `README.md`/dot-dir skipped,
deterministic ordering, and malformed-frontmatter skip.

## Phase 3 — `goals skills` command group
**Default: no install.** goals loads its own skills from the bundled dir, so
`goals skills list` and the visual builder work out of the box. Installing into
agent dirs is an *optional escape hatch* whose only purpose is invoking a skill
(e.g. `/decision-explainer`) inside a raw Claude/Codex session that never goes
through goals. Most users never need it.

- `goals skills list` — render discovered skills + per-skill source/agent
  availability. (This is the surface the visual builder reuses.)
- `goals skills install --target claude|codex|both [--force]` — OPTIONAL. Copy
  `bundled_skills_root()/*` into the chosen dir(s). `--target` required (no
  interactive default, no nudge). Idempotent (skip identical; `--force`
  overwrites). Reports installed/skipped.
- Keep `cli.py` thin: commands call `skill_discovery` helpers.

**Verify (tests):** `list` shows bundled skills with zero install; `install
--target` writes the chosen dir(s); second run is a no-op; `--force` overwrites;
installed skills then appear in `list` with the new source.

## Phase 4 — Retire the catalog (decouple, then delete)
Order matters — decouple the kept policy engine **before** deleting models.

1. **Decouple `permission_policy.py`:** drop the `EcosystemRecommendation`
   import. Make `goals permission check` evaluate a generic subject
   (kind/name/label/keywords) via the existing `evaluate_permission` core. Remove
   `apply_permission_to_recommendation` (orphan — only ecosystem used it) and
   `permission_report_for_recommendations` (or re-express over the generic
   subject). Keep `permissions.yml` and the policy semantics identical.
2. **`mode_a.py`:** remove `recommended_tools` construction + rendering and the
   hard-coded `goals ecosystem merge` handoff guidance. Drop `recommended_tools`
   from `ModeAPlan` (models.py:710).
3. **`dashboard.py`:** repoint the panel to live discovery — rename it "Skills,"
   replace `_recommendations_html` with rendering of `discover_skills()` output
   (same content as `goals skills list`: name, description, source/agent
   availability). Keep the nav link (relabel to "Skills").
4. **`memory.py`:** repoint the "ecosystem" friction area to `goals skills`
   (hint + change text), or rename the area to "skills."
5. **Delete:** `registries/skills.yml`, `registries/plugins.yml`,
   `src/goals/ecosystem.py`, the `goals ecosystem recommend|merge` CLI, the
   `Ecosystem*` models in `models.py`, and `tests/test_ecosystem.py`.
6. **Clean** the dangling `gates.yml` → `safety-check.scanners: [...]` ref
   (`scanners.py` was deleted earlier).

**Verify:** no dangling imports; `ruff` clean; full `pytest` green;
`grep -rn "ecosystem\|skills.yml\|plugins.yml" src/` returns zero code refs;
`goals permission check` still works against a generic subject; loading a
pre-change goal.json still succeeds (no persisted ecosystem data).

## Phase 5 — Docs + dogfood
- Update `README.md`, `docs/SELF_EVOLUTION.md`, `ROADMAP.md`: describe live
  discovery + optional `goals skills install`; remove `ecosystem recommend/merge`
  and any plugin-recommendation references.
- Dogfood: on a clean machine with nothing installed, `goals skills list` shows
  this repo's two native skills loaded from the bundled dir — that's the
  acceptance proof.

**Verify:** docs reference no removed commands; the clean-machine `goals skills
list` proof holds.

---

## Decisions to confirm before execution
1. **Bundled location** → repo-root `skills/` sources + hatch `force-include` →
   `goals/bundled_skills` in the wheel, read via `bundled_skills_root()`
   (packaged-first, repo-root fallback). Confirms "copyable source" + "actually
   ships." *Recommended.*
2. **Command shape** → `goals skills list|install` group. *Confirmed.*
3. **No install by default.** *Confirmed.*
4. **Dashboard panel** → *Decided:* repoint to live discovery — rename "Skills,"
   render `discover_skills()` output. A goal-scoped "attached skills" view arrives
   later with the visual builder.
5. **Plugins** → *Decided:* dropped entirely, no replacement.

## Definition of done
Live `SKILL.md` discovery is the only skill mechanism; goals' two native skills
load from the bundled dir with zero setup and ship correctly in a wheel; the
catalog, its models, its commands, and its couplings are gone; `goals permission
check` and existing goal files still work; suite green; docs accurate.

## Out of scope (next initiative)
The visual goal-loop builder (`docs/VISUAL_BUILDER_GOAL.md`) consumes
`discover_skills` once this lands.
