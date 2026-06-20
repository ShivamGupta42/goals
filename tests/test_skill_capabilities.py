from pathlib import Path

from goals.skill_capabilities import analyze_skill_capabilities, quarantine_skill
from goals.skill_discovery import DiscoveredSkill


def _skill(
    name: str,
    *,
    capabilities: list[str],
    sources: list[str],
    agents: list[str],
) -> DiscoveredSkill:
    return DiscoveredSkill(
        name=name,
        description="Skill used for tests.",
        capabilities=capabilities,
        sources=sources,
        agents=agents,
        path=f"/tmp/{name}/SKILL.md",
    )


def test_skill_preflight_requires_agent_available_skills() -> None:
    objective = "Build a frontend landing page"

    installed = analyze_skill_capabilities(
        objective,
        skills=[
            _skill(
                "frontend-builder",
                capabilities=["frontend-build", "product-ux-review"],
                sources=["codex"],
                agents=["codex"],
            )
        ],
    )
    assert installed.passed is True
    assert {finding.status for finding in installed.findings} == {"installed"}

    bundled_only = analyze_skill_capabilities(
        objective,
        skills=[
            _skill(
                "frontend-builder",
                capabilities=["frontend-build", "product-ux-review"],
                sources=["bundled"],
                agents=[],
            )
        ],
    )
    assert bundled_only.passed is False
    assert {finding.status for finding in bundled_only.findings} == {"bundled-only"}

    other_agent = analyze_skill_capabilities(
        objective,
        skills=[
            _skill(
                "frontend-builder",
                capabilities=["frontend-build", "product-ux-review"],
                sources=["claude"],
                agents=["claude"],
            )
        ],
    )
    assert other_agent.passed is False
    assert {finding.status for finding in other_agent.findings} == {"other-agent"}


def test_external_skill_import_enters_quarantine_before_trust(tmp_path: Path) -> None:
    source = tmp_path / "external"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\n"
        "name: external-ux\n"
        "description: Product UX review helper.\n"
        "capabilities:\n"
        "  - product-ux-review\n"
        "---\n"
        "# External UX\n",
        encoding="utf-8",
    )
    quarantine_root = tmp_path / "quarantine"

    target = quarantine_skill(source, "External UX", root=quarantine_root)
    report = analyze_skill_capabilities(
        "Run UX critique for a landing page",
        skills=[],
        quarantined_root=quarantine_root,
    )

    assert target == quarantine_root / "external-ux"
    assert target.joinpath("SKILL.md").is_file()
    assert report.passed is False
    assert any(finding.status == "quarantined" for finding in report.findings)
