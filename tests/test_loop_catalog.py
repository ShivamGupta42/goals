import io
import json
from pathlib import Path

import pytest

from goals import loop_catalog
from goals.loop_catalog import LoopSourceDocument, import_loop_design, list_loop_candidates
from goals.loop_builder import LoopDesign, LoopPhase, to_snapshot, with_validation_profiles
from goals.loop_check import check_loop
from goals.storage import GoalsError
from goals.validation_profiles import apply_validation_profiles


def _catalog(path: Path) -> Path:
    payload = {
        "updated": "2026-06-20",
        "loops": [
            {
                "slug": "quality-streak-loop",
                "title": "The quality streak loop",
                "category": {"label": "Evaluation"},
                "useWhen": "Use when the latest [N] realistic cases must pass in a row.",
                "verification": {
                    "title": "The latest [N] realistic cases pass in a row.",
                    "detail": "Every earlier failure is documented and protected.",
                },
                "steps": [
                    "Define realistic scenarios and the value of [N].",
                    "Run cases one at a time and preserve the result for review.",
                    "Stop only after [N] consecutive cases meet the original quality bar.",
                ],
            },
            {
                "slug": "fresh-clone-loop",
                "title": "The fresh-clone loop",
                "steps": ["Clone the repo in a clean environment."],
            },
        ],
    }
    path.write_text(json.dumps(payload))
    return path


def test_lists_catalog_candidates(tmp_path: Path) -> None:
    candidates = list_loop_candidates(_catalog(tmp_path / "catalog.json"))

    assert [candidate.candidate_id for candidate in candidates] == [
        "quality-streak-loop",
        "fresh-clone-loop",
    ]


def test_imports_loop_library_catalog_with_answers_and_profiles(tmp_path: Path) -> None:
    result = import_loop_design(
        _catalog(tmp_path / "catalog.json"),
        select="quality-streak-loop",
        answers={"N": "5"},
        root=tmp_path,
    )

    design = result.design
    assert design.objective == "The quality streak loop"
    assert "[N]" not in design.model_dump_json()
    assert "5 realistic cases" in design.why
    assert [phase.phase_id for phase in design.phases] == ["P1", "P2", "P3"]
    assert design.source_metadata is not None
    assert design.source_metadata.source.endswith("catalog.json")
    assert design.source_metadata.content_sha256
    assert design.phases[0].validation_profiles == ["imported-loop"]
    assert "browser-ux-loop" not in design.phases[0].validation_profiles
    assert any("Suggested validation profile" in warning for warning in result.warnings)
    assert not any("Candidate results" in item for item in design.phases[0].acceptance_criteria)
    projected = with_validation_profiles(design)
    assert any(
        "Evidence is recorded against the imported loop step" in item
        for item in projected.phases[0].acceptance_criteria
    )
    assert result.questions[0].token == "N"


def test_html_fallback_hashes_effective_catalog_source(tmp_path: Path) -> None:
    landing_url = "https://example.test/loop-library/"
    catalog_url = landing_url + "catalog.json"
    catalog_text = json.dumps(
        {
            "loops": [
                {
                    "slug": "single-loop",
                    "title": "Single loop",
                    "steps": ["Do it."],
                    "verification": "Done.",
                }
            ]
        }
    )

    class LandingReader:
        calls: list[str]

        def __init__(self) -> None:
            self.calls = []

        def read(self, source: str | Path, *, root: Path | None = None) -> LoopSourceDocument:
            label = str(source)
            self.calls.append(label)
            if label == landing_url:
                return LoopSourceDocument(source=label, text="<html>Loop Library</html>")
            if label == catalog_url:
                return LoopSourceDocument(source=label, text=catalog_text)
            raise AssertionError(f"Unexpected source read: {label}")

    reader = LandingReader()
    result = import_loop_design(
        landing_url,
        source_reader=reader,
        root=tmp_path,
    )

    assert result.design.source_metadata is not None
    metadata = result.design.source_metadata
    assert metadata.source == landing_url
    assert metadata.effective_source == catalog_url
    assert metadata.source_sha256 != metadata.content_sha256
    assert metadata.content_sha256
    assert reader.calls == [landing_url, catalog_url]
    assert "Read catalog JSON" in result.warnings[0]


def test_import_requires_selection_for_multi_loop_catalog(tmp_path: Path) -> None:
    with pytest.raises(GoalsError, match="Choose one with --select"):
        import_loop_design(_catalog(tmp_path / "catalog.json"), root=tmp_path)


def test_import_requires_placeholder_answers_without_prompt(tmp_path: Path) -> None:
    with pytest.raises(GoalsError, match="needs answers"):
        import_loop_design(
            _catalog(tmp_path / "catalog.json"),
            select="quality-streak-loop",
            root=tmp_path,
        )


def test_missing_answer_error_shows_repeated_answer_flags(tmp_path: Path) -> None:
    weak = tmp_path / "weak.json"
    weak.write_text(json.dumps({"title": "Weak loop"}))

    with pytest.raises(GoalsError) as exc:
        import_loop_design(weak, root=tmp_path)

    message = str(exc.value)
    assert "--answer first_step=..." in message
    assert "--answer verification=..." in message


def test_import_requires_missing_stop_condition_without_prompt(tmp_path: Path) -> None:
    weak = tmp_path / "weak.json"
    weak.write_text(json.dumps({"title": "Weak loop", "steps": ["Do the thing."]}))

    with pytest.raises(GoalsError, match="verification"):
        import_loop_design(weak, root=tmp_path)


def test_import_selects_untitled_catalog_loop_by_generated_candidate_id(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "loops": [
                    {
                        "steps": ["Do the untitled loop work."],
                        "verification": "The untitled loop is done.",
                    }
                ]
            }
        )
    )

    result = import_loop_design(
        catalog,
        select="loop-1",
        answers={"objective": "Untitled catalog loop"},
        root=tmp_path,
    )

    assert result.selected == "loop-1"
    assert result.design.phases[0].goal == "Do the untitled loop work."
    assert result.design.definition_of_done == ["The untitled loop is done."]


def test_stdin_import_rejects_oversized_input(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStdin:
        buffer = io.BytesIO(b"12345")

    monkeypatch.setattr(loop_catalog, "_MAX_SOURCE_BYTES", 4)
    monkeypatch.setattr(loop_catalog.sys, "stdin", FakeStdin())

    with pytest.raises(GoalsError, match="stdin is too large"):
        import_loop_design("-")


def test_placeholder_named_verification_does_not_satisfy_readiness(tmp_path: Path) -> None:
    weak = tmp_path / "weak.json"
    weak.write_text(json.dumps({"title": "Weak loop", "steps": ["Do [verification]."]}))

    with pytest.raises(GoalsError, match="readiness.verification"):
        import_loop_design(
            weak,
            answers={"verification": "the placeholder value"},
            root=tmp_path,
        )

    result = import_loop_design(
        weak,
        answers={
            "verification": "the placeholder value",
            "readiness.verification": "A test passes.",
        },
        root=tmp_path,
    )

    assert result.design.phases[0].goal == "Do the placeholder value."
    assert result.design.definition_of_done == ["A test passes."]
    assert result.design.phases[0].termination_conditions == ["A test passes."]


def test_import_can_answer_readiness_questions(tmp_path: Path) -> None:
    weak = tmp_path / "weak.json"
    weak.write_text(json.dumps({"title": "Weak loop"}))

    result = import_loop_design(
        weak,
        answers={
            "first_step": "Inspect the repository.",
            "verification": "A test passes.",
        },
        root=tmp_path,
    )

    assert result.design.phases[0].goal == "Inspect the repository."
    assert result.design.definition_of_done == ["A test passes."]
    assert result.design.phases[0].termination_conditions == ["A test passes."]
    assert not any("Missing required import detail" in warning for warning in result.warnings)


def test_imports_builder_script_without_running_save(tmp_path: Path) -> None:
    script = tmp_path / "demo.loop"
    script.write_text(
        "\n".join(
            [
                "objective Script loop",
                "add Plan :: Make a plan",
                "accept A test passes.",
                "save",
            ]
        )
    )

    result = import_loop_design(script, root=tmp_path)

    assert result.design.objective == "Script loop"
    assert result.design.phases[0].title == "Plan"
    assert not (tmp_path / "loop-design.json").exists()


def test_validation_profile_expansion_is_idempotent() -> None:
    design = LoopDesign(
        objective="Imported",
        phases=[LoopPhase(phase_id="P1", title="Plan", validation_profiles=["imported-loop"])],
    )

    once = apply_validation_profiles(design)
    twice = apply_validation_profiles(once.design)

    assert once.applied
    assert twice.applied == []
    assert len(once.design.phases[0].acceptance_criteria) == 1


def test_to_snapshot_expands_profiles_without_mutating_design() -> None:
    design = LoopDesign(
        objective="Imported",
        phases=[LoopPhase(phase_id="P1", title="Plan", validation_profiles=["imported-loop"])],
    )

    snapshot = to_snapshot(design)

    assert design.phases[0].acceptance_criteria == []
    assert any("Evidence is recorded" in item for item in snapshot.phases[0].acceptance_criteria)


def test_loop_check_flags_unknown_validation_profile() -> None:
    design = LoopDesign(
        objective="Bad profile",
        phases=[
            LoopPhase(
                phase_id="P1",
                title="Plan",
                acceptance_criteria=["A test passes."],
                termination_conditions=["Done."],
                validation_profiles=["missing-profile"],
            )
        ],
    )

    report = check_loop(design, skills=[], profiles={})

    assert "unknown-validation-profile" in {finding.code for finding in report.findings}
