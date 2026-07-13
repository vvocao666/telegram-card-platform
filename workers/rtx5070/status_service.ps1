param(
    [string]$ServiceName = "RTX5070_OCR",
    [int]$Port = 8000,
    [string]$AppDir = "D:\gpu_ocr"
)

$ErrorActionPreference = "Continue"

Write-Host "Service status:"
sc.exe query $ServiceName

Write-Host ""
Write-Host "PowerShell service view:"
Get-Service -Name $ServiceName -ErrorAction SilentlyContinue | Format-List Name,Status,StartType,ServiceType

Write-Host ""
Write-Host "Local health:"
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
} catch {
    Write-Host "Health check failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Listening port:"
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess

Write-Host ""
Write-Host "Recent logs:"
$logsDir = Join-Path $AppDir "logs"
$outLog = Join-Path $logsDir "ocr-worker.out.log"
$errLog = Join-Path $logsDir "ocr-worker.err.log"
if (Test-Path -LiteralPath $outLog) {
    Write-Host "--- stdout ---"
    Get-Content -LiteralPath $outLog -Tail 30
}
if (Test-Path -LiteralPath $errLog) {
    Write-Host "--- stderr ---"
    Get-Content -LiteralPath $errLog -Tail 30
}

