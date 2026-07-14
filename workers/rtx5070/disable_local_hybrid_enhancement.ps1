$ErrorActionPreference = 'Stop'
$envPath = 'D:\gpu_ocr\hybrid.env'
$lines = if (Test-Path $envPath) { Get-Content $envPath } else { @() }
$found = $false
$out = foreach ($line in $lines) { if ($line -match '^\s*LOCAL_HYBRID_ENHANCEMENT_ENABLED=') { $found = $true; 'LOCAL_HYBRID_ENHANCEMENT_ENABLED=false' } else { $line } }
if (-not $found) { $out += 'LOCAL_HYBRID_ENHANCEMENT_ENABLED=false' }
$out | Set-Content -Encoding utf8 $envPath
Restart-Service RTX5070_OCR
Get-Service RTX5070_OCR
