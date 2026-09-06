$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $projectPython -m uvicorn disaster.v2.api:app --host 127.0.0.1 --port 8800
