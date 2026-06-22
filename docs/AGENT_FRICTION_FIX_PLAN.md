# Fix Plan — Agent-experience friction (E1–E5)

Surfaced by driving a real 4-phase goal end-to-end and critiquing the experience
(see `skills/goals-critique/references/example-critique-thinking-gym.md`). Theme:
**rules are enforced in code but surfaced only in code** — an agent discovers them
by failing, not before. Each fix moves a rule from "learned via error" to
"known before authoring."

Priority: **P1** = pays off on every goal · **P2** = removes a specific stall ·
**P3** = nice-to-have.

---

## E1 — Evidence schema is invisible until violated  · **P1**

**Problem.** `Evidence` is `extra="forbid"` (`src/goals/models.py:225`) with 11
fixed fields (`:224-237`); `artifacts` must be `EvidenceArtifact` objects, not
strings. Authoring an extra key (`summary`) or string artifacts yields a raw
pydantic error. `goals phase evidence` help is one line (`cli.py:1751`); `goals
next` has no machine-readable schema (`next_command` flags are only
`--agent`/`--full`, `cli.py:301-322`).

**Fix.**
1. Add `goals next --json` that includes an `evidence_template` (the existing
   `ModeAPlan.evidence_template` is built but never surfaced) — field names, types,
   required-vs-optional, and a note that `ran/passed` are engine-owned.
2. Catch `ValidationError` in `phase_evidence()` and re-raise a friendly message:
   name the offending key(s) and print the allowed field set.

**Test.** `goals next --json | jq .evidence_template` is non-empty; feeding evidence
with an unknown key exits non-zero with a message naming the key (not a pydantic trace).
**Effort.** S–M.  **Risk.** Low (additive).

---

## E2 — "Engine owns ran/passed" is undocumented at point of use  · **P1**

**Problem.** `storage.py:222-231` strips agent-set `ran/passed/exit_code` on every
evidence record (correct integrity design), but nothing says so until
`goals phase review` fails with "not verified by execution." Agents reasonably set
`passed:true` and are silently overridden.

**Fix.**
1. One line in `phase evidence` help: "Verifications declare *what* will be checked;
   `ran`/`passed` are set only by `goals phase verify`."
2. When incoming evidence has non-default `ran`/`passed`, emit a notice:
   "ignored agent-set results on N verification(s) — run `goals phase verify`."

**Test.** Recording evidence with `passed:true` prints the notice; stored value is `false`.
**Effort.** S.  **Risk.** Low.

---

## E3 — Load-bearing assumptions need an *auto* falsifier; the error doesn't say so · **P1**

**Problem.** `gates.py:166-180` requires, per load-bearing assumption, a verification
with `kind=="auto" and ran and passed`. A *manual* verification counts for a normal
acceptance criterion (`_verification_counts_as_coverage`) but **not** for a
load-bearing assumption. The failure message is just
`"Load-bearing assumption has no passing falsifier (A-…)"` — the auto-vs-manual
asymmetry lives only in the docstring (`gates.py:97-98`).

**Fix.** Extend the message: "…needs an **auto** verification whose `covers` is this
assumption id and that ran & passed (a manual/waived check does not count for a
load-bearing assumption). Add one, or drop `--depends`."

**Test.** A goal with a load-bearing assumption covered only by a manual verification
fails review with the new wording.
**Effort.** S.  **Risk.** Low (message only).

---

## E4 — Breakdown ≠ phases, silently  · **P2**

**Problem.** A rich `goals assess breakdown` does **not** become phases; phases are
always the fixed 4-template (`runtime.py:42-83`, used at `:191`). The breakdown is
stored as a journey artifact. Reasonable, but an agent expecting sub-problems →
phases is briefly misled, and there's no documented path to custom phases.

**Fix.**
1. One sentence in `create`/`next` output: "Phases follow a fixed
   Confirm→Inspect→Execute→Review arc; your breakdown is the plan *inside* them."
2. Point to the real lever for custom phases: `goals loop build` → `goals loop
   activate` (confirm this is the supported path; document it).

**Test.** `create`/`next` output contains the clarifying sentence; docs link the
loop path.
**Effort.** S (docs) / M (if loop-activate needs polish).  **Risk.** Low.

---

## E5 — No nudge to learn at goal completion  · **P3** (this PR seeds it)

**Problem.** Completing a goal ends the loop; there's no prompt to retrospect, so
lessons evaporate. (The new `goals-critique` skill exists but nothing surfaces it.)

**Fix.**
1. (This PR) `commands/create.md` now suggests `/goals:critique` at completion.
2. (Follow-up) Have the final `goals next` handoff (when `goals check` is complete)
   or `goals finish` print: "Optional: run `/goals:critique` to capture lessons."
   It already suggests `goals user interview`; add critique beside it.

**Test.** Completion handoff text mentions the critique step.
**Effort.** S.  **Risk.** Low.

---

## Sequencing

1. **E1, E2, E3** together — all are "surface the contract before failure," small,
   low-risk, highest per-goal payoff. One PR.
2. **E4, E5** docs/handoff polish — can ride along or follow.

Recommend executing this as its own Goals goal (dogfood): the gates will force
each fix to carry a falsifier, which is exactly the discipline E1–E3 are about.
