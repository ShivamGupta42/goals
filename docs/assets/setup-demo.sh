#!/usr/bin/env bash
# Build a REAL Goals demo in /tmp so the hero GIF shows genuine, current state:
# a started goal with a recorded building journey and two phases accepted only
# after executed-proof checks actually ran. Idempotent: rerun any time.
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

goals start "ship the export endpoint" --in-place >/dev/null

# Building journey: one plain-English assumption + a breakdown.
goals assess assume "I'm assuming the export endpoint returns JSON, not a file download" \
  --building "the export endpoint" --toward "shipping the right thing" \
  --status holding --phase P1 >/dev/null
goals assess breakdown \
  --problem "Ship an export endpoint that returns the data as JSON" \
  --subproblem "Return JSON from app.export() | wire the route | confirm shape" >/dev/null

# --- P1: confirm outcome — executed-proof checks for each criterion ---
cat > /tmp/ev1.json <<'JSON'
{
  "changed_files": ["app.py"],
  "checks_run": ["python -c 'import app; assert app.export()[\"ok\"]'"],
  "verifications": [
    {"verification_id":"V-export-json","covers":"P1.C1","kind":"auto","command":"python3 -c \"import app; assert app.export()['ok'] is True\"","rationale":"Export returns JSON with ok=True.","ran":false,"passed":false,"output_excerpt":"","ran_at":"","exit_code":null,"output_sha256":""},
    {"verification_id":"V-plan-visible","covers":"P1.C2","kind":"auto","command":"test -f app.py && grep -q 'def export' app.py","rationale":"The target is visible as code.","ran":false,"passed":false,"output_excerpt":"","ran_at":"","exit_code":null,"output_sha256":""},
    {"verification_id":"V-next-open","covers":"P1.C3","kind":"auto","command":"goals check --json | python3 -c \"import sys,json; sys.exit(0 if json.load(sys.stdin).get('waiting_on','agent')=='agent' else 1)\"","rationale":"Next phase is unblocked.","ran":false,"passed":false,"output_excerpt":"","ran_at":"","exit_code":null,"output_sha256":""}
  ],
  "artifacts": [], "acceptance_met": [], "acceptance_not_met": [],
  "ambiguous": [], "known_gaps": [], "source_ids": [],
  "confidence": 0.9, "notes": "Confirmed: export endpoint returns JSON."
}
JSON
goals phase evidence P1 --file /tmp/ev1.json >/dev/null
goals phase verify P1 >/dev/null
goals phase review P1 >/dev/null
goals phase accept P1 >/dev/null

# --- P2: inspect + choose approach — record the approach, prove with checks ---
printf '# Approach\n- Return JSON from app.export(); risk: callers may expect a file download.\n' > NOTES.md
cat > /tmp/ev2.json <<'JSON'
{
  "changed_files": ["NOTES.md"],
  "checks_run": ["test -f app.py", "test -f NOTES.md"],
  "verifications": [
    {"verification_id":"V-files","covers":"P2.C1","kind":"auto","command":"test -f app.py && grep -q 'def export' app.py","rationale":"Relevant file/function identified.","ran":false,"passed":false,"output_excerpt":"","ran_at":"","exit_code":null,"output_sha256":""},
    {"verification_id":"V-risks","covers":"P2.C2","kind":"auto","command":"test -s NOTES.md && grep -qi 'risk' NOTES.md","rationale":"Repo-specific risk recorded.","ran":false,"passed":false,"output_excerpt":"","ran_at":"","exit_code":null,"output_sha256":""}
  ],
  "artifacts": [], "acceptance_met": [], "acceptance_not_met": [],
  "ambiguous": [], "known_gaps": [], "source_ids": [],
  "confidence": 0.9, "notes": "Approach and risk recorded."
}
JSON
goals phase evidence P2 --file /tmp/ev2.json >/dev/null
goals phase verify P2 >/dev/null
goals phase review P2 >/dev/null
goals phase accept P2 >/dev/null

echo "demo ready in $DEMO (2/4 phases accepted, executed proof recorded)"
