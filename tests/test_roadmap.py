from pathlib import Path

from goals.models import SelfCheckReport
from goals.roadmap import (
    END_MARKER,
    START_MARKER,
    apply_roadmap_update,
    plan_roadmap_update,
    render_roadmap_update_plan,
    suggestions_from_self_check,
    upsert_generated_section,
)


def test_roadmap_suggestions_from_self_check_are_public_safe(tmp_path: Path) -> None:
    report = SelfCheckReport(
        passed=True,
        summary="Ran self-check across 2 adapter shape(s): 2 pass, 0 fail.",
        next_slices=[
            "Explore planned capability: automatic gap-to-roadmap patches",
            "Close current capability gap: source freshness gate",
        ],
    )

    plan = plan_roadmap_update(tmp_path, report=report)
    rendered = render_roadmap_update_plan(plan)

    assert plan.path == "ROADMAP.md"
    assert plan.dry_run is True
    assert len(plan.suggestions) == 2
    assert plan.suggestions[0].capability == "automatic_gap_to_roadmap_patch"
    assert plan.suggestions[0].priority == "p1"
    assert plan.suggestions[1].priority == "p0"
    assert START_MARKER in plan.patch_preview
    assert END_MARKER in plan.patch_preview
    assert str(tmp_path) not in rendered
    assert "Roadmap Update Plan" in rendered
    assert "automatic gap-to-roadmap patches" in rendered


def test_roadmap_apply_creates_or_replaces_only_generated_block(tmp_path: Path) -> None:
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text(
        "# Roadmap\n\nHuman notes stay here.\n\n"
        f"{START_MARKER}\nold generated text\n{END_MARKER}\n",
        encoding="utf-8",
    )
    report = SelfCheckReport(
        passed=True,
        summary="Self-check summary.",
        next_slices=["Explore planned capability: parallel worktree merge gates"],
    )
    plan = plan_roadmap_update(tmp_path, report=report)

    applied = apply_roadmap_update(tmp_path, plan)
    updated = roadmap.read_text(encoding="utf-8")

    assert applied.dry_run is False
    assert "Human notes stay here." in updated
    assert "old generated text" not in updated
    assert updated.count(START_MARKER) == 1
    assert updated.count(END_MARKER) == 1
    assert "parallel worktree merge gates" in updated


def test_upsert_generated_section_appends_when_markers_are_missing() -> None:
    generated = f"{START_MARKER}\nnew\n{END_MARKER}\n"

    updated = upsert_generated_section("# Roadmap\n", generated)

    assert updated == "# Roadmap\n\n" + generated


def test_suggestions_empty_when_self_check_has_no_next_slice() -> None:
    report = SelfCheckReport(passed=True, summary="No next slices.", next_slices=[])

    suggestions = suggestions_from_self_check(report)

    assert suggestions == []
