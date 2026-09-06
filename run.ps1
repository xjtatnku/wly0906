$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Virtual environment missing. Follow README.md to install dependencies.'
}
& $projectPython -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
