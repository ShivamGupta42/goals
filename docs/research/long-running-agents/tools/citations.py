"""Add citation counts (Semantic Scholar) to a verified pool.

Usage: python -I citations.py POOL_JSON OUT_JSON

POOL_JSON is the output of validate_pool.py. One batch request fetches every paper.
Semantic Scholar rate-limits anonymous callers, so a 429 is retried with a longer wait.
A paper Semantic Scholar does not know gets citation_count = null (shown as unknown).
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=citationCount,influentialCitationCount,year"
TRIES = 7


def post(ids: list[str]) -> list[dict | None]:
    body = json.dumps({"ids": [f"ARXIV:{i}" for i in ids]}).encode()
    request = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    wait = 8
    for attempt in range(1, TRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == TRIES:
                raise
            print(f"  429 from Semantic Scholar, waiting {wait}s (try {attempt}/{TRIES})")
            time.sleep(wait)
            wait *= 2
    return []


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads(src.read_text())
    papers = data["verified"]
    results = post([p["arxiv_id"] for p in papers])
    known = 0
    for paper, result in zip(papers, results, strict=True):
        if result is None:
            paper["citation_count"] = None
            paper["influential_citation_count"] = None
        else:
            paper["citation_count"] = result.get("citationCount")
            paper["influential_citation_count"] = result.get("influentialCitationCount")
            known += 1
    out.write_text(json.dumps(data, indent=2))
    print(f"citation counts found for {known} of {len(papers)} papers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
