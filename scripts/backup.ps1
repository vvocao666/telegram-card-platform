param(
    [string]$ProjectDir = (Resolve-Path ".").Path,
    [string]$BackupRoot = "",
    [switch]$IncludeEnv
)

$ErrorActionPreference = "Stop"

if (-not $BackupRoot) {
    $BackupRoot = Join-Path $ProjectDir "backups"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $BackupRoot "telegram-card-platform-$timestamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

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
    ".github"
)

if ($IncludeEnv) {
    $items += ".env"
}

foreach ($item in $items) {
    $source = Join-Path $ProjectDir $item
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $backupDir -Recurse -Force
    }
}

if (Test-Path -LiteralPath (Join-Path $ProjectDir "outputs")) {
    Copy-Item -LiteralPath (Join-Path $ProjectDir "outputs") -Destination $backupDir -Recurse -Force
}

Write-Host "Backup created: $backupDir"
