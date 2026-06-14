from pathlib import Path

from goals.workflows import _dashboard_link


def test_dashboard_link_is_clickable_file_uri(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.html"
    link = _dashboard_link(path)

    # A bare file:// URL terminals can linkify — not a backtick-wrapped path.
    assert link.startswith("file://")
    assert "`" not in link
    assert link.endswith("/dashboard.html")


def test_dashboard_link_encodes_spaces(tmp_path: Path) -> None:
    # Worktree directories can contain spaces; the URL must stay valid.
    spaced = tmp_path / "a goal dir" / "dashboard.html"
    spaced.parent.mkdir()
    link = _dashboard_link(spaced)

    assert " " not in link
    assert "%20" in link
