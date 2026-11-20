"""Download chosen papers (PDF) and clones of their official code, as untrusted data.

Usage: python -I fetch_papers.py RANKING_JSON PAPERS_DIR CODE_DIR OUT_JSON

For each picked paper: PAPERS_DIR/<id>/paper.pdf and paper.txt (text extracted with pypdf).
For each picked paper with a code_url: a shallow git clone in CODE_DIR/<owner>__<repo>.
Nothing downloaded is ever run. Writes a summary to OUT_JSON.
"""

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError


def download_pdf(arxiv_id: str, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / "paper.pdf"
    request = urllib.request.Request(
        f"https://arxiv.org/pdf/{arxiv_id}", headers={"User-Agent": "research-script"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        pdf.write_bytes(response.read())
    reader = PdfReader(str(pdf))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    (folder / "paper.txt").write_text(text)
    links = sorted(set(re.findall(r"github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_-]+", text)))[:8]
    return {"pages": len(reader.pages), "chars": len(text), "github_links_in_text": links}


def clone(url: str, code_dir: Path) -> dict:
    match = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)", url)
    if not match:
        return {"status": "not a github url"}
    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    target = code_dir / f"{owner}__{repo}"
    if target.exists():
        return {"status": "already cloned", "path": str(target)}
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "clone",
            "--depth",
            "1",
            "--quiet",
            f"https://github.com/{owner}/{repo}.git",
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
        env={
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(Path.home()),
        },
    )
    if result.returncode != 0:
        return {"status": "clone failed", "error": result.stderr.strip()[:200]}
    sha = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return {"status": "cloned", "path": str(target), "commit": sha}


def main() -> int:
    ranking, papers_dir, code_dir, out = (Path(p) for p in sys.argv[1:5])
    picked = [r for r in json.loads(ranking.read_text())["ranking"] if r["selected"]]
    code_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for row in picked:
        entry = {
            "arxiv_id": row["arxiv_id"],
            "title": row["title"],
            "code_url": row.get("code_url"),
        }
        try:
            entry["paper"] = download_pdf(row["arxiv_id"], papers_dir / row["arxiv_id"])
        except (
            OSError,
            ValueError,
            PyPdfError,
        ) as err:  # keep going: one bad download must not stop the others
            entry["paper"] = {"error": str(err)[:200]}
        time.sleep(3)
        if row.get("code_url"):
            entry["code"] = clone(row["code_url"], code_dir)
        summary.append(entry)
        print(entry["arxiv_id"], entry["paper"], entry.get("code", {}).get("status", "no code"))
    out.write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
