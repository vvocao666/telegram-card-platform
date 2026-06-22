param(
    [string]$TaskName = "RTX5070_OCR",
    [string]$AppDir = "D:\gpu_ocr",
    [string]$PythonExe = "D:\gpu_ocr\venv\Scripts\python.exe",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $AppDir)) {
    throw "OCR worker directory not found: $AppDir"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$arguments = "-m uvicorn server:app --host $HostAddress --port $Port"
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $AppDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Start RTX5070 PaddleX OCR Worker on boot" `
    -RunLevel Highest `
    -Force

Write-Host "Created scheduled task: $TaskName"
Write-Host "Check command:"
Write-Host "schtasks /query /tn $TaskName"
Write-Host "Start now command:"
Write-Host "schtasks /run /tn $TaskName"
