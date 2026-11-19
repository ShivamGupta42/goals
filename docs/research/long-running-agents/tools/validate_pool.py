"""Verify candidate papers against arXiv and merge the per-theme pool files.

Usage: uv run --with defusedxml python -I validate_pool.py POOL_DIR OUT_JSON

Reads POOL_DIR/pool-T*.json (arrays of {arxiv_id, title, year, theme, type, why, code_url}).
For every id it asks the arXiv API for the real title, year and abstract. A paper is
verified only if the arXiv title matches the claimed title (similarity >= 0.8).
Writes {"verified": [...], "rejected": [...]} to OUT_JSON.
"""

import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from defusedxml import ElementTree as ET  # arXiv XML is network data: block entity attacks

NS = {"a": "http://www.w3.org/2005/Atom"}
BATCH = 40
MIN_SIMILARITY = 0.8
TRIES = 6


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip().removeprefix("arXiv:"))


def fetch_batch(ids: list[str]) -> dict[str, dict]:
    query = urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)})
    url = f"https://export.arxiv.org/api/query?{query}"
    wait = 10
    for attempt in range(1, TRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                root = ET.fromstring(response.read())
            break
        except urllib.error.HTTPError as err:
            if err.code not in (429, 503) or attempt == TRIES:
                raise
            print(f"  arXiv returned {err.code}, waiting {wait}s (try {attempt}/{TRIES})")
            time.sleep(wait)
            wait *= 2
    found: dict[str, dict] = {}
    for entry in root.findall("a:entry", NS):
        raw_id = entry.findtext("a:id", default="", namespaces=NS)
        arxiv_id = strip_version(raw_id.rsplit("/abs/", 1)[-1])
        title = " ".join(entry.findtext("a:title", default="", namespaces=NS).split())
        if not title or title.lower() == "error":
            continue
        found[arxiv_id] = {
            "title": title,
            "year": int(entry.findtext("a:published", default="0000", namespaces=NS)[:4]),
            "abstract": " ".join(entry.findtext("a:summary", default="", namespaces=NS).split()),
            "authors": [
                a.findtext("a:name", default="", namespaces=NS)
                for a in entry.findall("a:author", NS)
            ],
        }
    return found


def load_pool(pool_dir: Path) -> tuple[dict[str, dict], list[dict]]:
    merged: dict[str, dict] = {}
    problems: list[dict] = []
    for path in sorted(pool_dir.glob("pool-T*.json")):
        try:
            items = json.loads(path.read_text())
        except json.JSONDecodeError as err:
            problems.append({"file": path.name, "reason": f"invalid JSON: {err}"})
            continue
        for item in items:
            arxiv_id = strip_version(str(item.get("arxiv_id", "")))
            if not arxiv_id:
                problems.append({"file": path.name, "reason": "missing arxiv_id", "item": item})
                continue
            entry = merged.setdefault(arxiv_id, {**item, "arxiv_id": arxiv_id, "themes": []})
            theme = item.get("theme")
            if theme and theme not in entry["themes"]:
                entry["themes"].append(theme)
            if not entry.get("code_url") and item.get("code_url"):
                entry["code_url"] = item["code_url"]
    return merged, problems


def main() -> int:
    pool_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    merged, rejected = load_pool(pool_dir)
    ids = sorted(merged)
    real: dict[str, dict] = {}
    for start in range(0, len(ids), BATCH):
        real.update(fetch_batch(ids[start : start + BATCH]))
        time.sleep(3)  # arXiv asks for one request every 3 seconds
    verified = []
    for arxiv_id in ids:
        claimed = merged[arxiv_id]
        actual = real.get(arxiv_id)
        if actual is None:
            rejected.append(
                {
                    "arxiv_id": arxiv_id,
                    "reason": "not found on arXiv",
                    "claimed": claimed.get("title"),
                }
            )
            continue
        ratio = difflib.SequenceMatcher(
            None, norm(claimed.get("title", "")), norm(actual["title"])
        ).ratio()
        if ratio < MIN_SIMILARITY:
            rejected.append(
                {
                    "arxiv_id": arxiv_id,
                    "reason": f"title mismatch ({ratio:.2f})",
                    "claimed": claimed.get("title"),
                    "arxiv_title": actual["title"],
                }
            )
            continue
        verified.append(
            {
                "arxiv_id": arxiv_id,
                "title": actual["title"],
                "year": actual["year"],
                "themes": claimed["themes"],
                "type": claimed.get("type"),
                "why": claimed.get("why"),
                "code_url": claimed.get("code_url"),
                "abstract": actual["abstract"],
                "authors": actual["authors"],
            }
        )
    out.write_text(json.dumps({"verified": verified, "rejected": rejected}, indent=2))
    print(
        f"pool files merged: {len(ids)} unique ids; verified={len(verified)} rejected={len(rejected)}"
    )
    for item in rejected:
        print("  REJECTED:", item.get("arxiv_id", item.get("file")), "-", item["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
