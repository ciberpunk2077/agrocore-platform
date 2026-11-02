param([ValidateRange(1024,65535)][int]$Port = 8011)
$ErrorActionPreference = 'Stop'
if ($Port -eq 8000) { throw 'Port 8000 belongs to the normal backend.' }
$demoPython = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
Push-Location $PSScriptRoot
try {
    & $demoPython -B -u manage.py serve_demo --settings=config.settings.demo_view --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Demo viewer refused or stopped; no automatic retry.' }
} finally { Pop-Location }
