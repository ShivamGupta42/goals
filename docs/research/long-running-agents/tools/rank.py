"""Rank papers by importance and pick the top N with theme coverage.

Usage: python -I rank.py POOL_WITH_CITATIONS RATER_A RATER_B OUT_JSON OUT_MD [TOP_N]

Score (each part 0 to 3, written down before any rating):
  reach      I = from citations per year: >=200 -> 3, >=50 -> 2, >=10 -> 1, else 0.
             Papers under 12 months old get at least 1 (too new for citations).
  relevance  R = mean of the two raters (relevance to long-running agents)
  evidence   E = mean of the two raters (strength of evidence)
  usefulness U = mean of the two raters (usefulness to a harness like Goals; official code counts)
  score = 0.3*I + 0.3*R + 0.2*E + 0.2*U, shown on a 0 to 100 scale.
Pick: top N by score, but every theme first gets its 3 best papers.
"""

import datetime as dt
import json
import sys
from pathlib import Path

WEIGHTS = {"I": 0.3, "R": 0.3, "E": 0.2, "U": 0.2}
PER_THEME = 3
NOW = dt.date(2026, 11, 19)


def reach(paper: dict) -> tuple[int, str]:
    citations = paper.get("citation_count")
    age_years = max((NOW - dt.date(paper["year"], 7, 1)).days / 365.25, 0.25)
    if citations is None:
        return (1 if age_years < 1 else 0), "citations unknown"
    per_year = citations / age_years
    score = 3 if per_year >= 200 else 2 if per_year >= 50 else 1 if per_year >= 10 else 0
    if age_years < 1:
        return max(score, 1), f"{citations} citations, under 1 year old"
    return score, f"{citations} citations, {per_year:.0f} per year"


def main() -> int:
    pool_path, a_path, b_path, out_json, out_md = (Path(p) for p in sys.argv[1:6])
    top_n = int(sys.argv[6]) if len(sys.argv) > 6 else 14
    papers = json.loads(pool_path.read_text())["verified"]
    rate_a = {r["arxiv_id"]: r for r in json.loads(a_path.read_text())}
    rate_b = {r["arxiv_id"]: r for r in json.loads(b_path.read_text())}
    rows = []
    for paper in papers:
        pid = paper["arxiv_id"]
        if pid not in rate_a or pid not in rate_b:
            print(f"  NOT RATED by both raters: {pid} {paper['title'][:60]}")
            continue
        i_score, i_note = reach(paper)
        parts = {"I": float(i_score)}
        disagree = []
        for key in ("R", "E", "U"):
            a, b = rate_a[pid][key], rate_b[pid][key]
            parts[key] = (a + b) / 2
            if abs(a - b) >= 2:
                disagree.append(f"{key}:{a}/{b}")
        score = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS) / 3 * 100
        rows.append(
            {
                "arxiv_id": pid,
                "title": paper["title"],
                "year": paper["year"],
                "themes": paper["themes"],
                "type": paper.get("type"),
                "code_url": paper.get("code_url"),
                "reach_note": i_note,
                **parts,
                "score": round(score, 1),
                "raters_disagree": disagree,
            }
        )
    rows.sort(key=lambda r: r["score"], reverse=True)
    chosen: list[str] = []
    for theme in sorted({t for r in rows for t in r["themes"][:1]}):
        in_theme = [r for r in rows if r["themes"][:1] == [theme]]
        chosen += [r["arxiv_id"] for r in in_theme[:PER_THEME]]
    for row in rows:
        if len(chosen) >= top_n:
            break
        if row["arxiv_id"] not in chosen:
            chosen.append(row["arxiv_id"])
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["selected"] = row["arxiv_id"] in chosen
    out_json.write_text(json.dumps({"top_n": top_n, "weights": WEIGHTS, "ranking": rows}, indent=2))
    lines = [
        "| Rank | Score | Paper | Year | Theme | Reach | Rel | Evid | Use | Code | Picked |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['rank']} | {r['score']} | [{r['title'][:70]}](https://arxiv.org/abs/{r['arxiv_id']}) | {r['year']} | "
            f"{','.join(r['themes'])} | {r['I']:.0f} | {r['R']:.1f} | {r['E']:.1f} | {r['U']:.1f} | "
            f"{'yes' if r['code_url'] else 'no'} | {'**yes**' if r['selected'] else ''} |"
        )
    out_md.write_text("\n".join(lines) + "\n")
    print(f"ranked {len(rows)} papers, picked {sum(r['selected'] for r in rows)}")
    flagged = [r for r in rows if r["raters_disagree"] and r["selected"]]
    for r in flagged:
        print(f"  raters disagree on picked paper {r['arxiv_id']}: {r['raters_disagree']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
