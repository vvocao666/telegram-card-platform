param(
    [string]$ProjectDir = (Resolve-Path ".").Path,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectDir

if (-not (Test-Path ".venv")) {
    & $Python -m venv .venv
}

$venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Fill BOT_TOKEN before starting."
}

& $venvPython -m py_compile bot.py services/runtime.py services/ledger/ledger_commands.py storage/repositories/ledger_storage.py
Write-Host "Deploy preparation finished: $ProjectDir"
