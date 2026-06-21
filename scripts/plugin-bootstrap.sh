#!/bin/sh
# Goals plugin bootstrap — makes the Claude Code plugin self-installing.
#
# The plugin's commands and hooks call the `goals` CLI. Rather than make users
# install the CLI separately, the plugin's lifecycle hooks run THROUGH this
# wrapper: the first time it runs, it installs `goals` from the plugin's own
# bundled source (CLAUDE_PLUGIN_ROOT is a checkout of the repo, so it has
# pyproject.toml + src/). Every later run fast-paths straight to the CLI.
#
# Contract (important):
#   - stdout carries ONLY the wrapped `goals` output (hooks read it as JSON),
#     so every diagnostic goes to stderr.
#   - fail-open: a session hook must never crash the session, so any failure
#     exits 0 silently instead of erroring.
#
# Usage: plugin-bootstrap.sh <goals args...>   e.g. plugin-bootstrap.sh hooks session-start

ensure_goals() {
    command -v goals >/dev/null 2>&1 && return 0

    # uv installs the CLI shim into ~/.local/bin — make sure it's visible first.
    PATH="$HOME/.local/bin:$PATH"
    export PATH
    command -v goals >/dev/null 2>&1 && return 0

    echo "→ Goals: first run — installing the CLI (one time)…" >&2

    if ! command -v uv >/dev/null 2>&1; then
        echo "→ Goals: installing uv (Python toolchain)…" >&2
        curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh >&2 2>&1 || true
        PATH="$HOME/.local/bin:$PATH"
        export PATH
    fi
    command -v uv >/dev/null 2>&1 || return 1

    # Install from the plugin's own bundled source (the cloned repo).
    root="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
    [ -n "$root" ] && [ -f "$root/pyproject.toml" ] || return 1
    uv tool install --force "$root" >&2 2>&1 || return 1

    PATH="$HOME/.local/bin:$PATH"
    export PATH
    command -v goals >/dev/null 2>&1
}

if ensure_goals; then
    exec goals "$@"
fi

# Could not provide the CLI — degrade silently so the session is never blocked.
exit 0
