# Critique — goal "keep refining this gym…" (thinking-gym)

Worked example of the `goals-critique` skill. Subject: a 4-phase goal that
shipped a new-user onboarding layer for the `thinking-gym` repo. Outcome:
complete, 4/4 phases accepted, but with **three avoidable friction stalls**.
Citations are into `~/Desktop/p_code/goals/src/goals/`.

## What went well

- **The verify-gate did its job.** Being unable to self-assert `passed` forced
  real executed checks. Every acceptance criterion ended up with a runnable falsifier.
- **The load-bearing-assumption gate caught a real scoping error** (see below) —
  annoying in the moment, correct in hindsight.
- **The cold-read validation** (a no-context agent re-reading the repo) was a far
  better DoD test than self-review. Worth making a standard P4 move.

## Engine / UX friction → upstream actions

**E1 — Evidence schema is invisible until you violate it.**
`Evidence` is `extra="forbid"` (`models.py:225`) with 11 specific fields
(`models.py:224-237`); `artifacts` must be `EvidenceArtifact` objects (`path`,
`sha256`, `size_bytes`), not strings. I authored a `summary` key and string
artifacts and got a **raw pydantic error**. `goals phase evidence` help is one line
("Record phase evidence from a JSON object.", `cli.py:1751`) and shows no schema;
`goals next` has no `--json` to emit the template (`next_command` flags are only
`--agent`/`--full`, `cli.py:301-322`).
→ **Fix:** add `goals next --json` (or `goals phase evidence --schema`) that prints
the Evidence/Verification field list; make the validation error name the offending
key and the allowed set. *Cost of absence to me: 2 failed submissions + a source read.*

**E2 — The "engine owns ran/passed" rule is undocumented at the point of use.**
`storage.py:222-231` strips agent-set `ran/passed/exit_code` on every evidence
record (good design), but nothing in `phase evidence` help says so. An agent
reasonably sets `passed:true` and is silently overridden, then confused when review
says "not verified by execution."
→ **Fix:** one line in `phase evidence` help + a notice when incoming evidence has
non-default `ran/passed` ("ignored — run `goals phase verify`").

**E3 — Load-bearing assumptions need an *auto* falsifier; the failure message
doesn't say that.** `gates.py:166-180` requires `kind=="auto" and ran and passed`
for each load-bearing assumption, but a *manual* verification counts for a normal
criterion (`_verification_counts_as_coverage`, `gates.py:~205`). The review error is
just `"Load-bearing assumption has no passing falsifier (A-…)"` — it never explains
the auto-vs-manual asymmetry. I had to read `gates.py` to learn it.
→ **Fix:** extend the message: "…needs an *auto* verification whose `covers` is this
id and that ran & passed; manual/waived don't count for load-bearing assumptions."

**E4 — Breakdown ≠ phases, silently.** I authored a 5-sub-problem
`goals assess breakdown`; phases stayed the fixed 4-template from
`default_phases()` (`runtime.py:42-83`). The breakdown only became a "journey"
artifact. This is reasonable, but **undocumented** — I briefly expected my
sub-problems to be the phases.
→ **Fix:** one sentence in `create`/`next` output: "Phases follow a fixed
Confirm→Inspect→Execute→Review arc; your breakdown is the plan *inside* them. To
drive phases from a design, use `goals loop build`/`activate`."

## Agent-execution friction → recorded lessons

**A1 — I authored evidence without first confirming the schema.** Root cause:
assumed a permissive shape. Fix next time: before the first `phase evidence`, dump
the model fields (or read `models.py:224-237`) and author to them exactly. *(memory:
gate/learning)*

**A2 — I mis-scoped the load-bearing assumption to P2.** I attached "docs-not-
software" to P2, where it had no runnable falsifier, and review failed. The honest
falsifier (the cold-read) only existed in P4. Fix: **place a load-bearing assumption
on the phase that can actually test it**, not the phase where you first think it.
*(memory: gate/learning, the highest-value lesson here)*

**A3 — I didn't run `goals phase verify` until review forced it.** I treated
`evidence` as the end of a phase. Fix: the per-phase rhythm is
**evidence → verify → review → accept**, always four steps. *(memory: phase/friction)*

## Root causes

- Two of three stalls (E1/A1, E3/A2) share one root: **the schema and gate rules
  are enforced by code but surfaced only in code** — discoverable after failure, not
  before. The engine optimizes for integrity (correctly) but not for first-try
  agent success.
- My own root cause: I **acted before reading the contract**, twice. The verify
  loop is cheap to learn once; I paid the tuition in retries.

## Next-time changes (the point of the retro)

1. Before any `phase evidence`: author to the exact `Evidence`/`Verification` fields; no extras.
2. Attach each load-bearing assumption to the phase whose work can falsify it.
3. Run the full `evidence → verify → review → accept` rhythm every phase by default.
4. Keep the cold-read-by-no-context-agent as the standard P4 validation move.
5. (Upstream) land E1–E4 so the next agent doesn't pay the same tuition.
