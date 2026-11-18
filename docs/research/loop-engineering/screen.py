"""Screen loop-engineering candidates on GitHub. Usage: screen.py OUT_JSON README_CACHE_DIR"""

import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys

OUT, CACHE = sys.argv[1], sys.argv[2]
os.makedirs(CACHE, exist_ok=True)

# (repo, readme path inside repo or None for root README, group)
CANDIDATES = [
    ("cobusgreyling/loop-engineering", None, "named framework"),
    ("valkor-ai/loom", None, "named framework"),
    ("agentic-in/inferoa", None, "named framework"),
    ("ChaoYue0307/awesome-loop-engineering", None, "named framework"),
    ("snarktank/ralph", None, "ralph-style runner"),
    ("anthropics/claude-plugins-official", "plugins/ralph-loop/README.md", "ralph-style runner"),
    ("AnandChowdhary/continuous-claude", None, "ralph-style runner"),
    ("tzachbon/smart-ralph", None, "ralph-style runner"),
    ("computerlovetech/ralphify", None, "ralph-style runner"),
    ("parcadei/Continuous-Claude-v3", None, "state and handoff"),
    ("AMAP-ML/LoopArena", None, "measurement"),
    ("HKUDS/DeepCode", None, "agentic platform"),
]

LOOP = re.compile(r"\b(loop|cycle|iterat|repair|retr(y|ies)|recursive|repeat)", re.IGNORECASE)
CHECK = re.compile(r"\b(test|verif|check|review|criteria|validate|lint)", re.IGNORECASE)


def gh(path, jq):
    r = subprocess.run(["gh", "api", path, "--jq", jq], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {r.stderr.strip()[:200]}")
    return r.stdout


now = dt.datetime.now(dt.UTC)
rows = []
for repo, readme_path, group in CANDIDATES:
    meta = json.loads(
        gh(
            f"repos/{repo}",
            '{stars:.stargazers_count,license:(.license.key // "none"),pushed:.pushed_at,'
            'archived:.archived,language:(.language // "none"),description:(.description // "")}',
        )
    )
    path = f"repos/{repo}/contents/{readme_path}" if readme_path else f"repos/{repo}/readme"
    text = base64.b64decode(gh(path, ".content")).decode("utf-8", "replace")
    with open(os.path.join(CACHE, repo.replace("/", "__") + ".md"), "w") as f:
        f.write(text)
    pushed = dt.datetime.fromisoformat(meta["pushed"])
    rows.append(
        {
            "repo": repo,
            "group": group,
            "readme_path": readme_path or "README",
            "stars": meta["stars"],
            "license": meta["license"],
            "language": meta["language"],
            "archived": meta["archived"],
            "pushed": meta["pushed"][:10],
            "days_since_push": (now - pushed).days,
            "description": meta["description"][:160],
            "readme_chars": len(text),
            "loop_mentions": len(LOOP.findall(text)),
            "check_mentions": len(CHECK.findall(text)),
        }
    )

with open(OUT, "w") as f:
    json.dump(
        {
            "snapshot_date": now.date().isoformat(),
            "screen": "not archived, pushed within 365 days, README loop-words>=3 and check-words>=1",
            "screen_note": "First pass counted only the word 'loop'; valkor-ai/loom scored 2 (README lines 52-54 describe plan, build, check, repair, check again). Widened loop-words to loop|cycle|iterat|repair|retry|recursive|repeat.",
            "candidates": rows,
        },
        f,
        indent=2,
    )

for r in rows:
    ok = (
        (not r["archived"])
        and r["days_since_push"] <= 365
        and r["loop_mentions"] >= 3
        and r["check_mentions"] >= 1
    )
    print(
        f"{'PASS' if ok else 'FAIL'} {r['repo']:42} {r['stars']:>6}★ {r['license']:<10} push {r['pushed']} "
        f"loop={r['loop_mentions']:<3} check={r['check_mentions']:<3} {r['language']}"
    )
