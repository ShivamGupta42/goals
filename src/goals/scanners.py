from __future__ import annotations

import re
from pathlib import Path

from goals.models import GateVerdict, ScanResult

TEXT_EXTENSIONS = {".md", ".py", ".toml", ".yaml", ".yml", ".json", ".jsonl", ".html", ".txt"}
ALLOW_LINE = "goals-safety: allow"
ALLOW_BEGIN = "goals-safety: allow-begin"
ALLOW_END = "goals-safety: allow-end"

# goals-safety: allow-begin
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
]
LOCAL_PATH = re.compile(r"(/Users/[^\\s'\"<>]+|C:\\\\Users\\\\[^\\s'\"<>]+)")  # goals-safety: allow
PROMPT_INJECTION = re.compile(
    r"(?i)(ignore (all )?(previous|prior) instructions|disable safety-check)"
)  # goals-safety: allow
DESTRUCTIVE = re.compile(
    r"(?i)(rm -rf /|force-push|git push --force|wipe home)"
)  # goals-safety: allow
# goals-safety: allow-end


def run_safety_scanners(root: Path) -> list[ScanResult]:
    files = list(iter_text_files(root))
    results = [
        _scan_regex("secrets", files, SECRET_PATTERNS),
        _scan_regex("local_paths", files, [LOCAL_PATH]),
        _scan_regex("prompt_injection", files, [PROMPT_INJECTION]),
        _scan_regex("destructive_ops", files, [DESTRUCTIVE]),
        _scan_generated_state(root),
        _scan_license(root),
        _scan_supply_chain(files),
    ]
    return results


def iter_text_files(root: Path):
    ignored = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    for path in root.rglob("*"):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file() and path.suffix in TEXT_EXTENSIONS:
            yield path


def _scan_regex(name: str, files, patterns: list[re.Pattern[str]]) -> ScanResult:
    findings: list[str] = []
    for path in files:
        lines = path.read_text(errors="ignore").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if _is_allowed_line(lines, line_number - 1):
                continue
            for pattern in patterns:
                if pattern.search(line):
                    findings.append(f"{path}:{line_number}")
                    break
    return ScanResult(
        scanner=name,
        verdict=GateVerdict.FAIL if findings else GateVerdict.PASS,
        findings=sorted(set(findings)),
    )


def _is_allowed_line(lines: list[str], index: int) -> bool:
    if ALLOW_LINE in lines[index]:
        return True
    for prior in reversed(lines[:index]):
        if ALLOW_END in prior:
            return False
        if ALLOW_BEGIN in prior:
            return True
    return False


def _scan_generated_state(root: Path) -> ScanResult:
    generated = (
        [str(p) for p in (root / ".agent-workflow" / "goals").rglob("*") if p.is_file()]
        if (root / ".agent-workflow" / "goals").exists()
        else []
    )
    return ScanResult(
        scanner="public_repo_hygiene",
        verdict=GateVerdict.FAIL if generated else GateVerdict.PASS,
        findings=generated,
    )


def _scan_license(root: Path) -> ScanResult:
    findings = []
    if not (root / "LICENSE").exists():
        findings.append("LICENSE file is missing.")
    return ScanResult(
        scanner="license",
        verdict=GateVerdict.FAIL if findings else GateVerdict.PASS,
        findings=findings,
    )


def _scan_supply_chain(files) -> ScanResult:
    findings: list[str] = []
    for path in files:
        if path.suffix not in {".yaml", ".yml"}:
            continue
        text = path.read_text(errors="ignore")
        if "http://" in text:
            findings.append(f"{path}: insecure external reference")
    return ScanResult(
        scanner="supply_chain",
        verdict=GateVerdict.FAIL if findings else GateVerdict.PASS,
        findings=findings,
    )
