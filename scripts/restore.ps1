param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir,
    [string]$ProjectDir = (Resolve-Path ".").Path,
    [switch]$IncludeEnv
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $BackupDir)) {
    throw "Backup directory not found: $BackupDir"
}

$items = @(
    "bot.py",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "pytest.ini",
    "VERSION",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "DEPLOY.md",
    "MAINTENANCE.md",
    "config",
    "handlers",
    "services",
    "storage",
    "utils",
    "docs",
    "scripts",
    "systemd",
    "tests",
    "feature_backups",
    ".github",
    "outputs"
)

if ($IncludeEnv) {
    $items += ".env"
}

foreach ($item in $items) {
    $source = Join-Path $BackupDir $item
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $ProjectDir -Recurse -Force
    }
}

Write-Host "Restore finished from: $BackupDir"
