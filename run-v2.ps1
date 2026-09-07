$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS = '1' }
if (-not $env:OPENBLAS_NUM_THREADS) { $env:OPENBLAS_NUM_THREADS = '1' }
& $projectPython -m uvicorn disaster.v2.api:app --host 127.0.0.1 --port 8800
