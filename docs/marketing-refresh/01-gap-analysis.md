# Gap analysis — `marketing` branch vs. current architecture

**Phase P2 deliverable.** Inventories every asset on the local `marketing` branch
and classifies each against the code on `main` today. Method: read each asset,
then grep the whole branch for the five recent features and check claims against
`src/goals/`, `commands/`, and `registries/`.

## Headline finding (falsifiable)

A grep of **every** `.md` file on the `marketing` branch for
`skill-first | trust v1 | capability gap | executed proof | building journey | pacers`
returns **zero matches**. The entire kit was written at/before commit `a99f27d`
and predates the five changes now on the main line. Reproduce:

```bash
git ls-tree -r --name-only marketing | grep '\.md$' | while read f; do
  git show "marketing:$f" | grep -ciE 'skill-first|trust v1|capability gap|executed proof|building journey|pacers'
done   # all zero
```

## Asset inventory (what's on the branch)

| Asset | Purpose | Verdict |
| --- | --- | --- |
| `README.md` (rewritten) | No-nonsense positioning, install, command set | **Accurate base, incomplete** — positioning current; missing the 5 new features; prose-first not demo-first; no architecture diagram |
| `docs/marketing/01-distribution-research.md` | Channel research (HN, marketplaces, Reddit, X) | **Accurate** — strategy is feature-agnostic; keep as-is |
| `docs/marketing/02-goals-marketing-plan.md` | Positioning + sequenced channel plan + metrics | **Accurate** — locked positioning matches `pyproject` |
| `docs/marketing/03-launch-assets.md` | One-liners, About/topics, Show HN, X, Reddit blurbs | **Stale claims** — copy describes durability/evidence but omits executed-proof, skill-first, Trust V1, readable journey |
| `docs/marketing/04-demo-production-guide.md` | Demo theory/guide | **Accurate** — method fine; shot content needs new beats |
| `docs/marketing/05-goals-demo-production-plan.md` | VHS `.tape` hero-GIF recipe | **Stale shot list** — 5-beat demo shows start→check→/clear→resume; doesn't show the building journey or executed-proof gate |
| `docs/marketing/06-readme-draft.md` | Proposed quickstart-first README restructure | **Good skeleton, incomplete** — reorg is right; content predates new features + no diagram |
| `docs/marketing/07-awesome-list-and-marketplace.md` | Submission targets + status (ComposioHQ PR, hesreallyhim) | **Accurate, actionable** — keep; live submission status tracked |
| `docs/marketing/08-launch-copy.md` | Rewritten launch copy (new positioning) | **Stale claims** — same omission as 03 |
| `docs/marketing/README.md` | Marketing workspace index + locked positioning | **Accurate index** — positioning locked; doesn't index diagrams (none exist) |
| `assets/*.gif / *.mp4 / *.tape` | Hero GIF + product video + VHS tapes | **Needs re-record** — captures old flow; flagged as out-of-scope follow-up |
| `assets/dashboard-hero.png` `@2x` | Dashboard hero screenshot | **Likely stale** — predates PACERS building-journey dashboard reframe (#18) |
| `install.sh` / `install.ps1` | One-line installers | **Accurate** — current; already on `main` too |

## What's stale: the 5 missing features (and where the code proves them)

| Feature (PR) | What it means for users | Code proof | Where it must appear |
| --- | --- | --- | --- |
| **Executed-proof gates** (#19, #20) | A phase passes only when runnable checks actually execute and exit 0 — a pass is *earned*, not asserted | `src/goals/gates.py` (`review_phase` — "Gate a phase on *executed* proof"), `runtime.py`, `storage.py` | Hero claim in README + launch copy; demo beat |
| **PACERS building journey** (#18) | The dashboard shows a plain-English trace of *why* the agent did things, with assumptions you can read | `src/goals/journey.py`, `assess` CLI, `dashboard.py` | README "how it works" + a screenshot + demo beat |
| **Skill-first architecture** (#22) | Goals discovers and uses agent skills live from `SKILL.md`, bundled in the wheel | `src/goals/skill_discovery.py`, `skill_capabilities.py`, `skills/` | README "how it works" + architecture diagram |
| **Trust V1 — capability-gap mgmt** (#21) | Goals checks it *has the skills/tools* a goal needs before working, and surfaces gaps | `src/goals/capabilities.py`, `goals capability check`, `registries/` | A feature bullet + launch copy |
| **Typed gate findings** (#20) | Gate findings are typed kernel facts with a read-time verdict rubric | `src/goals/gates.py`, `rubric.py` | Supports the "evidence-based done" claim |

## Repo-specific risks & constraints (P2.C2)

1. **Doc-honesty is test-enforced.** `tests/test_skill_hygiene.py` fails on stale
   `goals ...` CLI examples. Any command shown in new copy must be a real Typer
   command (verified against `goals --help`). Constraint, not a blocker.
2. **Diagrams will drift if drawn from prose.** Must be sourced from
   `src/goals/` module/command names (load-bearing assumption A-0e66d1ee).
3. **Positioning is locked** to "a no-nonsense goal workflow engine"
   (`pyproject.toml` + marketing README). Refresh keeps the voice; no repositioning.
4. **Screen-capture assets can't be produced headlessly.** Hero GIF + product
   video re-record and the dashboard hero screenshot need a terminal recorder
   (VHS) and a live dashboard — flagged as a follow-up, not done in this goal.
5. **`marketing` branch is unmerged and parallel.** Treat as source material;
   produce refreshed outputs on the current branch under `docs/marketing-refresh/`
   to avoid a risky cross-branch merge mid-goal.
6. **Two audiences, one honesty line.** Copy must lead with users who can act
   today (Claude Code / Codex) and never claim the AI runs autonomously — Goals
   runs the *workflow*, the agent does the *work*.

## Chosen approach (lowest-risk path)

Keep the strong, feature-agnostic assets (01, 02, 04, 07) as-is. **Refresh** the
claim-bearing copy (03, 06, 08, README) to add the 5 features. **Create** the
missing architecture diagrams (P3) and fold them into a single refreshed launch
kit + index (P4). **Flag** all screen-capture work as a follow-up. Outputs land in
`docs/marketing-refresh/` so nothing on `marketing` or `main` is destructively
touched.
