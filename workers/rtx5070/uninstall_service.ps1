param(
    [string]$ServiceName = "RTX5070_OCR",
    [string]$AppDir = "D:\gpu_ocr"
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run this script in an Administrator PowerShell."
    }
}

function Get-NssmPath {
    $command = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $candidates = @(
        (Join-Path $AppDir "nssm.exe"),
        (Join-Path $AppDir "tools\nssm\nssm.exe"),
        (Join-Path $AppDir "tools\nssm\nwin64\nssm.exe"),
        (Join-Path $AppDir "tools\nssm-2.24\win64\nssm.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

Assert-Administrator

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Service not found: $ServiceName"
    exit 0
}

$nssm = Get-NssmPath
if ($nssm) {
    Write-Host "Stopping service with NSSM..."
    & $nssm stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "Removing service with NSSM..."
    & $nssm remove $ServiceName confirm | Out-Null
} else {
    Write-Host "NSSM not found. Removing service with sc.exe..."
    sc.exe stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    sc.exe delete $ServiceName | Out-Null
}

Write-Host "Service removed: $ServiceName"
Write-Host "Verify:"
Write-Host "  sc query $ServiceName"

