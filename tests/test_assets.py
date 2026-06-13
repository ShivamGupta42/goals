from pathlib import Path

from goals.assets import analyze_asset_provenance, render_asset_provenance_report
from goals.models import AssetRecord, GoalSnapshot, SourceRecord, WorktreeLease
from goals.runtime import default_phases


def snapshot_with_assets(tmp_path: Path, assets: list[AssetRecord]) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Create campaign assets",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Create campaign assets"),
        current_phase="P1",
        assets=assets,
        sources=[
            SourceRecord(
                source_id="SRC-license",
                title="Asset license",
                source_type="document",
                summary="License note.",
            )
        ],
    )


def test_asset_provenance_passes_for_complete_generated_asset(tmp_path: Path) -> None:
    snapshot = snapshot_with_assets(
        tmp_path,
        [
            AssetRecord(
                title="Hero image",
                locator="assets/hero.png",
                asset_type="image",
                origin="generated",
                creator_tool="image model",
                usage_rights="allowed",
                source_ids=["SRC-license"],
                prompt="Abstract product hero on white background.",
            )
        ],
    )

    report = analyze_asset_provenance(snapshot)

    assert report.passed is True
    assert report.findings == []


def test_asset_provenance_finds_missing_rights_license_and_prompt(tmp_path: Path) -> None:
    local_locator = "/" + "Users/example/private/banner.png"
    snapshot = snapshot_with_assets(
        tmp_path,
        [
            AssetRecord(
                title="Stock banner",
                locator=local_locator,
                asset_type="image",
                origin="stock",
                usage_rights="unknown",
                source_ids=["SRC-missing"],
            ),
            AssetRecord(
                title="Generated social image",
                locator="assets/social.png",
                asset_type="image",
                origin="generated",
                usage_rights="allowed",
            ),
        ],
    )

    report = analyze_asset_provenance(snapshot)
    rendered = render_asset_provenance_report(report)

    assert report.passed is False
    assert any("local machine path" in finding.summary for finding in report.findings)
    assert any("license is missing" in finding.summary for finding in report.findings)
    assert any("usage rights are unknown" in finding.summary for finding in report.findings)
    assert any("missing source evidence" in finding.summary for finding in report.findings)
    assert any("generation prompt" in finding.summary for finding in report.findings)
    assert "Asset Provenance Report" in rendered
    assert "Agent Can Work On" in rendered


def test_asset_provenance_surfaces_blocked_or_restricted_rights(tmp_path: Path) -> None:
    snapshot = snapshot_with_assets(
        tmp_path,
        [
            AssetRecord(
                title="Restricted logo",
                locator="assets/logo.png",
                asset_type="image",
                origin="external",
                license="Vendor license",
                usage_rights="restricted",
            ),
            AssetRecord(
                title="Blocked photo",
                locator="assets/photo.png",
                asset_type="image",
                origin="external",
                license="Do not use",
                usage_rights="blocked",
            ),
        ],
    )

    report = analyze_asset_provenance(snapshot)

    assert report.passed is False
    assert "Asset has restricted usage rights: Restricted logo" in report.user_questions
    assert "Asset usage is blocked: Blocked photo" in report.user_questions
