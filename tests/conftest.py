import pytest

from goals.checkpoint_workflows import HOST_SESSION_ENV_VARS


@pytest.fixture(autouse=True)
def _no_host_session(monkeypatch) -> None:
    """Keep tests hermetic when the suite itself runs inside an agent host.

    Claude Code exports its session id to the agent's shell, and checkpoints
    asked while it's set only accept replies from that session. Tests that
    exercise session binding set it explicitly.
    """
    for name in HOST_SESSION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
