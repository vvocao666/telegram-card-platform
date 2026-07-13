param(
    [string]$ServiceName = "RTX5070_OCR",
    [string]$AppDir = "D:\gpu_ocr",
    [string]$PythonExe = "D:\gpu_ocr\venv\Scripts\python.exe",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Please run this script in an Administrator PowerShell."
    }
}

function Assert-PathExists {
    param([string]$Path, [string]$Message)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Message`: $Path"
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

    $toolsDir = Join-Path $AppDir "tools"
    $zipPath = Join-Path $toolsDir "nssm-2.24.zip"
    $extractDir = Join-Path $toolsDir "nssm-2.24"
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

    Write-Host "NSSM not found. Downloading NSSM 2.24..."
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zipPath
    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $toolsDir -Force

    $downloaded = Join-Path $extractDir "win64\nssm.exe"
    if (-not (Test-Path -LiteralPath $downloaded)) {
        throw "NSSM download failed: $downloaded"
    }
    return $downloaded
}

function Stop-ExistingWorkerOnPort {
    param([int]$Port, [string]$AppDir)

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $processId = [int]$listener.OwningProcess
        if ($processId -le 0) {
            continue
        }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        $commandLine = [string]$process.CommandLine
        $isGpuOcrWorker = $commandLine.Contains($AppDir) -and $commandLine.Contains("uvicorn") -and $commandLine.Contains("server:app")
        if (-not $isGpuOcrWorker) {
            throw "Port $Port is already used by PID $processId and does not look like this OCR worker: $commandLine"
        }
        Write-Host "Stopping existing manual OCR worker on port $Port, PID $processId..."
        Stop-Process -Id $processId -Force
        Start-Sleep -Seconds 2
    }
}

Assert-Administrator
Assert-PathExists -Path $AppDir -Message "OCR worker directory not found"
Assert-PathExists -Path $PythonExe -Message "Python executable not found"
Assert-PathExists -Path (Join-Path $AppDir "server.py") -Message "server.py not found"

$nssm = Get-NssmPath
$logsDir = Join-Path $AppDir "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$scheduledTask = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
if ($scheduledTask) {
    Write-Host "Removing old scheduled task $ServiceName..."
    Unregister-ScheduledTask -TaskName $ServiceName -Confirm:$false
}

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Existing service found. Stopping and removing $ServiceName..."
    & $nssm stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    & $nssm remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
}

Stop-ExistingWorkerOnPort -Port $Port -AppDir $AppDir

$arguments = "-m uvicorn server:app --host 0.0.0.0 --port $Port"
Write-Host "Installing service $ServiceName..."
& $nssm install $ServiceName $PythonExe $arguments | Out-Null
& $nssm set $ServiceName AppDirectory $AppDir | Out-Null
& $nssm set $ServiceName DisplayName "RTX5070 OCR Worker" | Out-Null
& $nssm set $ServiceName Description "PaddleX OCR worker for Telegram Card Platform" | Out-Null
& $nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
& $nssm set $ServiceName AppStdout (Join-Path $logsDir "ocr-worker.out.log") | Out-Null
& $nssm set $ServiceName AppStderr (Join-Path $logsDir "ocr-worker.err.log") | Out-Null
& $nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $nssm set $ServiceName AppRotateOnline 1 | Out-Null
& $nssm set $ServiceName AppRotateSeconds 86400 | Out-Null
& $nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
& $nssm set $ServiceName AppThrottle 1500 | Out-Null
& $nssm set $ServiceName AppExit Default Restart | Out-Null

sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/10000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null

Write-Host "Starting service $ServiceName..."
& $nssm start $ServiceName | Out-Null
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Service installed."
Write-Host "Validation commands:"
Write-Host "  sc query $ServiceName"
Write-Host "  Get-Service $ServiceName"
Write-Host "  Invoke-RestMethod http://127.0.0.1:$Port/health"
Write-Host "  Get-Content $logsDir\ocr-worker.err.log -Tail 50"
Write-Host ""
sc.exe query $ServiceName

