# caishui-agents launcher (ASCII-only: compatible with Windows PowerShell 5.1 and pwsh)
$ErrorActionPreference = "Stop"
try {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) { throw "python not found (need Python 3.10+ on PATH)" }
  if (-not (Test-Path "$PSScriptRoot\config.json")) {
    Copy-Item "$PSScriptRoot\config.example.json" "$PSScriptRoot\config.json"
    Write-Host "config.json created from config.example.json"
  }
  & python "$PSScriptRoot\server.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "server exited with code $LASTEXITCODE"
    Read-Host "Press Enter to close" | Out-Null
  }
} catch {
  Write-Host "ERROR: $_"
  Read-Host "Press Enter to close" | Out-Null
}
