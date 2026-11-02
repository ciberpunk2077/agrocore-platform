$ErrorActionPreference = 'Stop'
$viewerPython = Join-Path $PSScriptRoot '..\.venv\Scripts\pythonw.exe'
$viewerScript = Join-Path $PSScriptRoot 'open_demo_credentials.py'
if (-not (Test-Path -LiteralPath $viewerPython)) { throw 'Python GUI del entorno local no disponible.' }
Start-Process -FilePath $viewerPython -ArgumentList @('-B', ('"' + $viewerScript + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
