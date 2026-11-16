# Stop caishui-agents (equivalent to the Exit button in the web UI)
$port = 8642
$cfg = Join-Path $PSScriptRoot "config.json"
if (Test-Path $cfg) {
  try { $port = (Get-Content $cfg -Raw | ConvertFrom-Json).port } catch { }
}
try {
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/shutdown" -TimeoutSec 5 | Out-Null
  Write-Host "caishui-agents stopped (port $port released)."
} catch {
  Write-Host "Service not running (port $port no response)."
}
