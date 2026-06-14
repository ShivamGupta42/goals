#!/bin/sh
# Goals — one-line installer.
#   curl -fsSL https://raw.githubusercontent.com/ShivamGupta42/goals/main/install.sh | sh
#
# Installs uv (if missing), then the `goals` CLI straight from GitHub — no clone,
# no PyPI, no separate Python install (uv provisions Python 3.11+ for you).
set -e

REPO="git+https://github.com/ShivamGupta42/goals.git"

echo "→ Installing Goals…"

# 1. Ensure uv is available.
if ! command -v uv >/dev/null 2>&1; then
  echo "→ uv not found — installing it first…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Install the goals CLI directly from GitHub.
uv tool install --force "$REPO"

echo ""
echo "✅ Goals is installed."
echo ""
echo "Next:"
echo "  goals setup --agent both     # connect Claude Code and/or Codex"
echo "  goals start \"build me a weight-loss tracking app\""

if ! command -v goals >/dev/null 2>&1; then
  echo ""
  echo "Note: open a new terminal (or add ~/.local/bin to your PATH) so 'goals' is found."
fi
