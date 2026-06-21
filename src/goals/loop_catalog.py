"""Import external loop definitions into Goals ``LoopDesign`` objects."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import yaml
from pydantic import BaseModel, ConfigDict, Field

from goals.git_ops import slugify
from goals.loop_builder import (
    BuilderResponse,
    BuilderSession,
    LoopDesign,
    LoopPhase,
    LoopSourceMetadata,
    apply_command,
)
from goals.storage import GoalsError


AskQuestion = Callable[["LoopImportQuestion"], str]
AskSelection = Callable[[list["LoopCandidate"]], str]

_PLACEHOLDER_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]{0,48})\]")
_MAX_TITLE = 72
_MAX_SOURCE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class LoopSourceDocument:
    source: str
    text: str


@dataclass(frozen=True)
class LoopPayloadDocument:
    payload: Any
    original: LoopSourceDocument
    effective: LoopSourceDocument
    warnings: list[str] = field(default_factory=list)


class LoopSourceReader(Protocol):
    def read(self, source: str | Path, *, root: Path | None = None) -> LoopSourceDocument:
        """Read a source into bounded UTF-8 text."""
        ...


class LoopCatalogAdapter(Protocol):
    def parse(
        self,
        document: LoopSourceDocument,
        *,
        source_reader: LoopSourceReader,
        root: Path | None = None,
    ) -> LoopPayloadDocument:
        """Parse a source document into a loop payload."""
        ...


class LoopNormalizer(Protocol):
    def candidates(self, payload: Any) -> list["LoopCandidate"]:
        """List importable loop candidates in a payload."""
        ...

    def select(
        self,
        payload: Any,
        select: str,
        ask_selection: AskSelection | None,
    ) -> tuple[Any, str]:
        """Select one loop payload from a source payload."""
        ...

    def design(self, payload: Any) -> LoopDesign:
        """Normalize one loop payload into a LoopDesign."""
        ...


class LoopCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    title: str
    source_kind: str = ""


class LoopImportQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    prompt: str
    default: str = ""
    kind: Literal["placeholder", "readiness"] = "placeholder"
    answer_key: str = ""


class LoopImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design: LoopDesign
    source: str
    selected: str = ""
    questions: list[LoopImportQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DefaultLoopSourceReader:
    def read(self, source: str | Path, *, root: Path | None = None) -> LoopSourceDocument:
        text, source_label = _read_source(source, root=root)
        return LoopSourceDocument(source=source_label, text=text)


class DefaultLoopCatalogAdapter:
    def parse(
        self,
        document: LoopSourceDocument,
        *,
        source_reader: LoopSourceReader,
        root: Path | None = None,
    ) -> LoopPayloadDocument:
        return _parse_payload(document, source_reader=source_reader, root=root)


class DefaultLoopNormalizer:
    def candidates(self, payload: Any) -> list[LoopCandidate]:
        return _candidates(payload)

    def select(
        self,
        payload: Any,
        select: str,
        ask_selection: AskSelection | None,
    ) -> tuple[Any, str]:
        return _select_loop(payload, select, ask_selection)

    def design(self, payload: Any) -> LoopDesign:
        return _design_from_payload(payload)


def import_loop_design(
    source: str | Path,
    *,
    select: str = "",
    answers: dict[str, str] | None = None,
    ask_question: AskQuestion | None = None,
    ask_selection: AskSelection | None = None,
    root: Path | None = None,
    source_reader: LoopSourceReader | None = None,
    catalog_adapter: LoopCatalogAdapter | None = None,
    normalizer: LoopNormalizer | None = None,
) -> LoopImportResult:
    """Read ``source`` and normalize one loop into a Goals ``LoopDesign``.

    ``source`` can be a URL, local file, local directory, ``file://`` URL, or
    ``-`` for stdin. JSON/YAML catalogs, single loop objects, LoopDesign JSON, and
    existing builder command scripts are supported.
    """
    reader = source_reader or DefaultLoopSourceReader()
    adapter = catalog_adapter or DefaultLoopCatalogAdapter()
    loop_normalizer = normalizer or DefaultLoopNormalizer()
    source_document = reader.read(source, root=root)
    payload_document = adapter.parse(source_document, source_reader=reader, root=root)
    selected_payload, selected = loop_normalizer.select(
        payload_document.payload,
        select,
        ask_selection,
    )
    design = loop_normalizer.design(selected_payload)
    warnings = list(payload_document.warnings)
    warnings += _profile_suggestion_warnings(selected_payload, design)
    warnings += _readiness_warnings(design)
    design.source_metadata = LoopSourceMetadata(
        source=payload_document.original.source,
        effective_source=payload_document.effective.source,
        source_sha256=sha256(payload_document.original.text.encode("utf-8")).hexdigest(),
        selected=selected,
        content_sha256=sha256(payload_document.effective.text.encode("utf-8")).hexdigest(),
        warnings=list(warnings),
    )
    questions = questions_for_design(design)
    normalized_answers = _normalize_answers(answers or {})
    missing = [question for question in questions if _answer_value(normalized_answers, question) is None]
    for question in missing:
        if ask_question is None:
            wanted = " ".join(f"--answer {_answer_key(q)}=..." for q in missing)
            raise GoalsError(
                "Imported loop needs answers for required details. "
                f"Re-run with {wanted} or run interactively."
            )
        normalized_answers[_answer_key(question)] = ask_question(question)
    if normalized_answers:
        design = apply_answers(design, normalized_answers, questions=questions)
        if design.source_metadata is not None:
            design.source_metadata.warnings = _readiness_warnings(design) + [
                warning
                for warning in design.source_metadata.warnings
                if not warning.startswith("Missing required import detail:")
            ]
    return LoopImportResult(
        design=design,
        source=payload_document.original.source,
        selected=selected,
        questions=questions,
        answers=normalized_answers,
        warnings=design.source_metadata.warnings if design.source_metadata else warnings,
    )


def list_loop_candidates(
    source: str | Path,
    *,
    root: Path | None = None,
    source_reader: LoopSourceReader | None = None,
    catalog_adapter: LoopCatalogAdapter | None = None,
    normalizer: LoopNormalizer | None = None,
) -> list[LoopCandidate]:
    reader = source_reader or DefaultLoopSourceReader()
    adapter = catalog_adapter or DefaultLoopCatalogAdapter()
    loop_normalizer = normalizer or DefaultLoopNormalizer()
    source_document = reader.read(source, root=root)
    payload_document = adapter.parse(source_document, source_reader=reader, root=root)
    return loop_normalizer.candidates(payload_document.payload)


def questions_for_design(design: LoopDesign) -> list[LoopImportQuestion]:
    tokens: list[str] = []
    questions: list[LoopImportQuestion] = []
    for text in _design_texts(design):
        for match in _PLACEHOLDER_RE.finditer(text):
            token = match.group(1)
            if token not in tokens:
                tokens.append(token)
                questions.append(
                    LoopImportQuestion(
                        token=token,
                        prompt=f"Value for [{token}]",
                        default="",
                        kind="placeholder",
                        answer_key=token,
                    )
                )
    questions.extend(_readiness_questions(design, placeholder_tokens=tokens))
    return questions


def apply_answers(
    design: LoopDesign,
    answers: dict[str, str],
    *,
    questions: list[LoopImportQuestion] | None = None,
) -> LoopDesign:
    normalized = _normalize_answers(answers)
    question_list = questions or []
    readiness_values = {
        q.token: value
        for q in question_list
        if q.kind == "readiness" and (value := _answer_value(normalized, q)) is not None
    }
    if question_list:
        placeholder_values = {
            q.token: value
            for q in question_list
            if q.kind == "placeholder" and (value := _answer_value(normalized, q)) is not None
        }
    else:
        placeholder_values = normalized

    def repl(text: str) -> str:
        for token, value in placeholder_values.items():
            text = text.replace(f"[{token}]", value)
        return text

    updated = design.model_copy(deep=True)
    if readiness_values.get("objective"):
        updated.objective = readiness_values["objective"]
    if readiness_values.get("first_step") and not updated.phases:
        updated.phases.append(
            LoopPhase(
                phase_id="P1",
                title=_title_from_step(readiness_values["first_step"], 1),
                goal=readiness_values["first_step"],
                validation_profiles=["imported-loop"],
            )
        )
    if readiness_values.get("verification"):
        verification = readiness_values["verification"]
        if verification not in updated.definition_of_done:
            updated.definition_of_done.append(verification)
        if updated.phases and verification not in updated.phases[-1].termination_conditions:
            updated.phases[-1].termination_conditions.append(verification)
        if updated.phases:
            criterion = f"Final verification passes: {verification}"
            if criterion not in updated.phases[-1].acceptance_criteria:
                updated.phases[-1].acceptance_criteria.append(criterion)
    updated.objective = repl(updated.objective)
    updated.why = repl(updated.why)
    updated.definition_of_done = [repl(item) for item in updated.definition_of_done]
    for phase in updated.phases:
        phase.title = repl(phase.title)
        phase.goal = repl(phase.goal)
        phase.acceptance_criteria = [repl(item) for item in phase.acceptance_criteria]
        phase.termination_conditions = [repl(item) for item in phase.termination_conditions]
    return updated


def render_import_result(result: LoopImportResult, *, design_path: str = "") -> str:
    lines = [
        f"Imported loop: {result.design.objective or 'Untitled loop'}",
        f"Source: {result.source}",
    ]
    metadata = result.design.source_metadata
    if metadata and metadata.effective_source and metadata.effective_source != metadata.source:
        lines.append(f"Effective source: {metadata.effective_source}")
    if result.selected:
        lines.append(f"Selected: {result.selected}")
    if result.answers:
        lines.append("Answers: " + ", ".join(f"{k}={v}" for k, v in sorted(result.answers.items())))
    if metadata and metadata.content_sha256:
        lines.append(f"Source hash: {metadata.content_sha256[:12]}")
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.append(f"Phases: {len(result.design.phases)}")
    if design_path:
        lines.append(f"Saved: {design_path}")
    return "\n".join(lines)


def _read_source(source: str | Path, *, root: Path | None = None) -> tuple[str, str]:
    source_text = str(source)
    if source_text == "-":
        return _read_stdin(), "stdin"
    if _is_url(source_text):
        return _read_url(source_text), source_text
    path = Path(source_text).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    if path.is_dir():
        for name in ("loop-design.json", "catalog.json", "loop.json", "loop.yml", "loop.yaml"):
            candidate = path / name
            if candidate.exists():
                return _read_file(candidate), str(candidate)
        loop_scripts = sorted(path.glob("*.loop"))
        if loop_scripts:
            return _read_file(loop_scripts[0]), str(loop_scripts[0])
        raise GoalsError(f"No importable loop file found in {path}.")
    if not path.exists():
        raise GoalsError(f"Loop source not found: {source}")
    return _read_file(path), str(path)


def _read_stdin() -> str:
    raw = sys.stdin.buffer.read(_MAX_SOURCE_BYTES + 1)
    if len(raw) > _MAX_SOURCE_BYTES:
        raise GoalsError(f"Loop source stdin is too large (max {_MAX_SOURCE_BYTES} bytes).")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GoalsError(f"Loop source stdin must be UTF-8 text: {exc}") from exc


def _read_file(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise GoalsError(f"Could not inspect loop source {path}: {exc}") from exc
    if size > _MAX_SOURCE_BYTES:
        raise GoalsError(f"Loop source is too large ({size} bytes; max {_MAX_SOURCE_BYTES}).")
    try:
        return _checked_text(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        raise GoalsError(f"Could not read loop source {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise GoalsError(f"Loop source {path} must be UTF-8 text: {exc}") from exc


def _checked_text(text: str, label: str) -> str:
    size = len(text.encode("utf-8"))
    if size > _MAX_SOURCE_BYTES:
        raise GoalsError(f"Loop source {label} is too large ({size} bytes; max {_MAX_SOURCE_BYTES}).")
    return text


def _read_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "goals-loop-import/0.1"})
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit user URL
            raw = response.read(_MAX_SOURCE_BYTES + 1)
            if len(raw) > _MAX_SOURCE_BYTES:
                raise GoalsError(
                    f"Loop URL response is too large (max {_MAX_SOURCE_BYTES} bytes)."
                )
            return raw.decode("utf-8")
    except HTTPError as exc:
        raise GoalsError(f"Could not read loop URL {url}: HTTP {exc.code} {exc.reason}") from exc
    except URLError as exc:
        raise GoalsError(f"Could not read loop URL {url}: {exc.reason}") from exc
    except UnicodeDecodeError as exc:
        raise GoalsError(f"Loop URL {url} must return UTF-8 text: {exc}") from exc


def _parse_payload(
    document: LoopSourceDocument,
    *,
    source_reader: LoopSourceReader,
    root: Path | None = None,
) -> LoopPayloadDocument:
    warnings: list[str] = []
    try:
        return LoopPayloadDocument(
            payload=json.loads(document.text),
            original=document,
            effective=document,
            warnings=warnings,
        )
    except json.JSONDecodeError:
        pass
    try:
        parsed = yaml.safe_load(document.text)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, (dict, list)):
        return LoopPayloadDocument(
            payload=parsed,
            original=document,
            effective=document,
            warnings=warnings,
        )
    if document.text.lstrip().startswith("<") and _is_url(document.source):
        catalog_url = urljoin(document.source.rstrip("/") + "/", "catalog.json")
        try:
            catalog_document = source_reader.read(catalog_url, root=root)
            return LoopPayloadDocument(
                payload=json.loads(catalog_document.text),
                original=document,
                effective=catalog_document,
                warnings=[f"Read catalog JSON from {catalog_url}"],
            )
        except Exception as exc:  # noqa: BLE001
            raise GoalsError(
                f"{document.source} looks like HTML and no catalog.json could be read: {exc}"
            ) from exc
    return LoopPayloadDocument(
        payload={"builder_script": document.text},
        original=document,
        effective=document,
        warnings=warnings,
    )


def _select_loop(payload: Any, select: str, ask_selection: AskSelection | None) -> tuple[Any, str]:
    candidates = _candidates(payload)
    if not candidates:
        return payload, ""
    if len(candidates) == 1 and not select:
        candidate = candidates[0]
        return _candidate_payload(payload, candidate.candidate_id), candidate.candidate_id
    if not select and ask_selection is not None:
        select = ask_selection(candidates)
    if not select:
        shown = ", ".join(f"{c.candidate_id} ({c.title})" for c in candidates[:8])
        more = f", +{len(candidates) - 8} more" if len(candidates) > 8 else ""
        raise GoalsError(f"Source contains multiple loops. Choose one with --select: {shown}{more}.")
    for candidate in candidates:
        if select in {candidate.candidate_id, slugify(candidate.title), candidate.title}:
            return _candidate_payload(payload, candidate.candidate_id), candidate.candidate_id
    raise GoalsError(f"No loop matching --select {select!r}.")


def _candidates(payload: Any) -> list[LoopCandidate]:
    loops = _loop_list(payload)
    return [_candidate_for_loop(loop, index) for index, loop in enumerate(loops, start=1)]


def _candidate_payload(payload: Any, candidate_id: str) -> Any:
    for index, loop in enumerate(_loop_list(payload), start=1):
        candidate = _candidate_for_loop(loop, index)
        ids = {candidate.candidate_id, slugify(candidate.title), candidate.title}
        if candidate_id in ids:
            return loop
    return payload


def _candidate_for_loop(loop: Any, index: int) -> LoopCandidate:
    title = _text(_get(loop, "title")) or _text(_get(loop, "objective")) or f"Loop {index}"
    candidate_id = _text(_get(loop, "slug")) or _text(_get(loop, "id")) or slugify(title)
    return LoopCandidate(
        candidate_id=candidate_id or f"loop-{index}",
        title=title,
        source_kind="catalog",
    )


def _loop_list(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        loops = payload.get("loops")
        if isinstance(loops, list):
            return loops
        items = payload.get("items")
        if isinstance(items, list):
            return items
    if isinstance(payload, list):
        return payload
    return []


def _design_from_payload(payload: Any) -> LoopDesign:
    if isinstance(payload, dict):
        if "builder_version" in payload or (
            isinstance(payload.get("phases"), list)
            and any(isinstance(p, dict) and "phase_id" in p for p in payload.get("phases", []))
        ):
            return LoopDesign.model_validate(payload)
        if "builder_script" in payload:
            return _design_from_script(str(payload["builder_script"]))
        return _design_from_mapping(payload)
    raise GoalsError("Loop source must contain a mapping, catalog, or builder script.")


def _design_from_script(script: str) -> LoopDesign:
    session = BuilderSession(design=LoopDesign(), out_dir=Path("."), skills=[])
    for line in script.splitlines():
        command = line.strip().split(" ", 1)[0].lower() if line.strip() else ""
        if command in {"save", "quit", "exit"}:
            continue
        response: BuilderResponse = apply_command(session, line)
        if response.message.startswith("Unknown command"):
            raise GoalsError(response.message)
    return session.design


def _design_from_mapping(data: dict[str, Any]) -> LoopDesign:
    objective = _text(data.get("objective")) or _text(data.get("title")) or "Imported loop"
    why = _text(data.get("why")) or _text(data.get("useWhen")) or _text(data.get("use_when"))
    verification = _verification_text(data.get("verification"))
    definition = _list_of_text(data.get("definition_of_done"))
    if verification and verification not in definition:
        definition.append(verification)
    source_profiles = _list_of_text(data.get("validation_profiles") or data.get("profiles"))
    raw_phases = data.get("phases")
    if isinstance(raw_phases, list):
        phases = [
            _phase_from_mapping(item, i, source_profiles=source_profiles)
            for i, item in enumerate(raw_phases, start=1)
        ]
    else:
        steps = _list_of_text(data.get("steps"))
        if not steps:
            prompt = _text(data.get("prompt"))
            steps = [prompt] if prompt else []
        phases = [
            _phase_from_step(step, i, len(steps), verification, source_profiles)
            for i, step in enumerate(steps, 1)
        ]
    if not phases and verification:
        phases = [_phase_from_step(verification, 1, 1, verification, source_profiles)]
    return LoopDesign(
        objective=objective,
        why=why,
        definition_of_done=definition,
        phases=phases,
    )


def _phase_from_mapping(
    item: Any,
    index: int,
    *,
    source_profiles: list[str] | None = None,
) -> LoopPhase:
    if not isinstance(item, dict):
        return _phase_from_step(_text(item), index, index, "", source_profiles or [])
    profiles = _list_of_text(item.get("validation_profiles") or item.get("profiles"))
    if not profiles:
        profiles = list(source_profiles or ["imported-loop"])
    return LoopPhase(
        phase_id=_text(item.get("phase_id")) or f"P{index}",
        title=_text(item.get("title")) or f"Step {index}",
        goal=_text(item.get("goal")) or _text(item.get("description")),
        acceptance_criteria=_list_of_text(item.get("acceptance_criteria") or item.get("acceptance")),
        termination_conditions=_list_of_text(
            item.get("termination_conditions") or item.get("termination")
        ),
        skills=_list_of_text(item.get("skills")),
        validation_profiles=profiles,
    )


def _phase_from_step(
    step: str,
    index: int,
    total: int,
    verification: str,
    profiles: list[str],
) -> LoopPhase:
    title = _title_from_step(step, index)
    phase_profiles = list(profiles or ["imported-loop"])
    acceptance = [f"Evidence is recorded for this imported loop step: {step}"]
    termination: list[str] = []
    if index == total and verification:
        acceptance.append(f"Final verification passes: {verification}")
        termination.append(verification)
    return LoopPhase(
        phase_id=f"P{index}",
        title=title,
        goal=step,
        acceptance_criteria=acceptance,
        termination_conditions=termination,
        validation_profiles=phase_profiles,
    )


def _profile_suggestion_warnings(payload: Any, design: LoopDesign) -> list[str]:
    if not isinstance(payload, dict):
        return []
    declared = bool(_list_of_text(payload.get("validation_profiles") or payload.get("profiles")))
    declared = declared or any(
        phase.validation_profiles and phase.validation_profiles != ["imported-loop"]
        for phase in design.phases
    )
    if declared:
        return []
    text = " ".join([json.dumps(payload, default=str), *_design_texts(design)])
    suggested = [p for p in _profiles_for_text(text) if p != "imported-loop"]
    if not suggested:
        return []
    joined = ", ".join(suggested)
    return [f"Suggested validation profile(s) not auto-applied: {joined}."]


def _readiness_questions(
    design: LoopDesign,
    *,
    placeholder_tokens: list[str],
) -> list[LoopImportQuestion]:
    questions: list[LoopImportQuestion] = []
    if design.objective.strip() in {"", "Imported loop"}:
        questions.append(
            _readiness_question(
                "objective",
                "What should this imported loop be called?",
                placeholder_tokens,
            )
        )
    if not design.phases:
        questions.append(
            _readiness_question(
                "first_step",
                "What is the first concrete step this loop should run?",
                placeholder_tokens,
            )
        )
    has_stop = bool(design.definition_of_done) or any(
        phase.termination_conditions or _has_authored_completion_criterion(phase)
        for phase in design.phases
    )
    if not has_stop:
        questions.append(
            _readiness_question(
                "verification",
                "What evidence proves this loop is done?",
                placeholder_tokens,
            )
        )
    return questions


def _readiness_question(
    token: str,
    prompt: str,
    placeholder_tokens: list[str],
) -> LoopImportQuestion:
    answer_key = f"readiness.{token}" if token in placeholder_tokens else token
    return LoopImportQuestion(
        token=token,
        prompt=prompt,
        kind="readiness",
        answer_key=answer_key,
    )


def _readiness_warnings(design: LoopDesign) -> list[str]:
    warnings: list[str] = []
    for question in _readiness_questions(design, placeholder_tokens=[]):
        warnings.append(f"Missing required import detail: {question.token}.")
    return warnings


def _profiles_for_text(text: str) -> list[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9]+", lowered))
    profiles = ["imported-loop"]
    if words & {
        "benchmark",
        "benchmarks",
        "coverage",
        "runtime",
        "speed",
        "measure",
        "measured",
    }:
        profiles.append("benchmark-loop")
    if words & {
        "browser",
        "browsers",
        "screenshot",
        "screenshots",
        "pixel",
        "pixels",
        "ui",
        "ux",
        "accessibility",
    }:
        profiles.append("browser-ux-loop")
    if words & {
        "candidate",
        "candidates",
        "champion",
        "holdout",
        "streak",
        "score",
        "experiment",
    }:
        profiles.append("experiment-loop")
    if (
        words & {"branch", "branches", "worktree", "worktrees", "repository", "repo", "commit"}
        or "pull request" in lowered
    ):
        profiles.append("repository-maintenance-loop")
    return profiles


def _has_authored_completion_criterion(phase: LoopPhase) -> bool:
    return any(
        criterion.strip()
        and not criterion.startswith("Evidence is recorded for this imported loop step:")
        for criterion in phase.acceptance_criteria
    )


def _title_from_step(step: str, index: int) -> str:
    cleaned = " ".join(step.split())
    if not cleaned:
        return f"Step {index}"
    if len(cleaned) <= _MAX_TITLE:
        return cleaned
    return cleaned[: _MAX_TITLE - 1].rstrip(" .,;:") + "…"


def _verification_text(value: Any) -> str:
    if isinstance(value, dict):
        title = _text(value.get("title"))
        detail = _text(value.get("detail")) or _text(value.get("description"))
        if title and detail:
            return f"{title.rstrip(' .')}: {detail}"
        return title or detail
    return _text(value)


def _design_texts(design: LoopDesign) -> list[str]:
    texts = [design.objective, design.why, *design.definition_of_done]
    for phase in design.phases:
        texts.extend(
            [
                phase.title,
                phase.goal,
                *phase.acceptance_criteria,
                *phase.termination_conditions,
            ]
        )
    return texts


def _answer_key(question: LoopImportQuestion) -> str:
    return question.answer_key or question.token


def _answer_value(
    answers: dict[str, str],
    question: LoopImportQuestion,
) -> str | None:
    key = _normalize_answer_key(_answer_key(question))
    if key in answers:
        return answers[key]
    scoped_key = _normalize_answer_key(f"{question.kind}.{question.token}")
    if scoped_key in answers:
        return answers[scoped_key]
    if key == question.token and question.token in answers:
        return answers[question.token]
    return None


def _normalize_answers(answers: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in answers.items():
        normalized[_normalize_answer_key(key)] = value
    return normalized


def _normalize_answer_key(key: str) -> str:
    token = key.strip().replace(":", ".")
    if token.startswith("[") and token.endswith("]"):
        token = token[1:-1]
    return token


def _list_of_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _is_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "file://"))
