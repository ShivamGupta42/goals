# Goals — one-line installer (Windows / PowerShell).
#   irm https://raw.githubusercontent.com/ShivamGupta42/goals/main/install.ps1 | iex
#
# Installs uv (if missing), then the `goals` CLI straight from GitHub — no clone,
# no PyPI, no separate Python install (uv provisions Python 3.11+ for you).
$ErrorActionPreference = "Stop"
$repo = "git+https://github.com/ShivamGupta42/goals.git"

Write-Host "-> Installing Goals..."

# 1. Ensure uv is available.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "-> uv not found - installing it first..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# 2. Install the goals CLI directly from GitHub.
uv tool install --force $repo

Write-Host ""
Write-Host "Goals is installed. Next:"
Write-Host "  goals setup --agent both     # connect Claude Code and/or Codex"
Write-Host '  goals start "build me a weight-loss tracking app"'
