#!/usr/bin/env bash
# Build a REAL Goals demo in /tmp so the hero GIF shows genuine state:
# a started goal, a recorded building journey, and a phase accepted only
# after an executed-proof check actually ran. Idempotent: rerun any time.
set -euo pipefail

DEMO=/tmp/goals-demo
rm -rf "$DEMO"
mkdir -p "$DEMO"
cd "$DEMO"

git init -q
git config user.email demo@example.com
git config user.name Demo
printf 'def export():\n    return {"ok": True}\n' > app.py
git add -A && git commit -qm init
git checkout -q -b dev

# Start a goal in place (dev branch, no worktree needed for the demo).
goals start "ship the export endpoint" --in-place >/dev/null

# Building journey: one plain-English, load-bearing assumption + a breakdown.
goals assess assume "I'm assuming the export endpoint returns JSON, not a file download" \
  --building "the export endpoint" --toward "shipping the right thing" \
  --status holding --phase P1 >/dev/null
goals assess breakdown \
  --problem "Ship an export endpoint that returns the data as JSON" \
  --subproblem "Return JSON from app.export() | wire the route | confirm shape" >/dev/null

# Executed-proof: a real check that runs and must exit 0.
cat > /tmp/ev.json <<'JSON'
{
  "changed_files": ["app.py"],
  "checks_run": ["python -c 'import app; assert app.export()[\"ok\"]'"],
  "verifications": [
    {
      "verification_id": "V-demo-export-json",
      "covers": "P1.C1",
      "kind": "auto",
      "command": "python3 -c \"import app; assert app.export()['ok'] is True\"",
      "rationale": "The export endpoint returns JSON with ok=True. Fails if the shape is wrong.",
      "ran": false, "passed": false, "output_excerpt": "",
      "ran_at": "", "exit_code": null, "output_sha256": ""
    },
    {
      "verification_id": "V-demo-plan-visible",
      "covers": "P1.C2",
      "kind": "auto",
      "command": "test -f app.py && grep -q 'def export' app.py",
      "rationale": "The plan/target is visible as code. Fails if app.py or the export function is missing.",
      "ran": false, "passed": false, "output_excerpt": "",
      "ran_at": "", "exit_code": null, "output_sha256": ""
    },
    {
      "verification_id": "V-demo-next-unblocked",
      "covers": "P1.C3",
      "kind": "auto",
      "command": "goals check --json | python3 -c \"import sys,json; sys.exit(0 if json.load(sys.stdin).get('waiting_on','agent')=='agent' else 1)\"",
      "rationale": "The next phase is unblocked: nothing is waiting on the user. Fails if the goal is blocked on a user decision.",
      "ran": false, "passed": false, "output_excerpt": "",
      "ran_at": "", "exit_code": null, "output_sha256": ""
    }
  ],
  "artifacts": [], "acceptance_met": [], "acceptance_not_met": [],
  "ambiguous": [], "known_gaps": [], "source_ids": [],
  "confidence": 0.9, "notes": "Demo: export endpoint returns JSON."
}
JSON

goals phase evidence P1 --file /tmp/ev.json >/dev/null
goals phase verify P1 >/dev/null
goals phase review P1 >/dev/null
goals phase accept P1 >/dev/null

echo "demo ready in $DEMO"
