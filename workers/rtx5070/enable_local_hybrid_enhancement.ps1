$ErrorActionPreference = 'Stop'
$envPath = 'D:\gpu_ocr\hybrid.env'
$values = @{
  LOCAL_HYBRID_ENHANCEMENT_ENABLED = 'true'; LOCAL_WORKER_QUEUE_V2_ENABLED = 'true';
  LOCAL_CPU_PREPROCESS_ENABLED = 'true'; LOCAL_CPU_OCR_ENABLED = 'true';
  LOCAL_CPU_OCR_SHADOW_ONLY = 'false'; LOCAL_CPU_OCR_CAN_AFFECT_RESULT = 'true';
  LOCAL_ROI_REVIEW_V2_ENABLED = 'true'; LOCAL_CPU_OCR_CONFIRMATION_MODE = 'strict'
}
$existing = @{}; if (Test-Path $envPath) { Get-Content $envPath | ForEach-Object { if ($_ -match '^\s*([^#=]+)=(.*)$') { $existing[$matches[1].Trim()] = $matches[2].Trim() } } }
$values.Keys | ForEach-Object { $existing[$_] = $values[$_] }
$existing.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" } | Set-Content -Encoding utf8 $envPath
Restart-Service RTX5070_OCR
Get-Service RTX5070_OCR
