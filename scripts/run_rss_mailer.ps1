# Windows 작업 스케줄러에서 호출용
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error ".venv 없음. 먼저: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

$env:PYTHONIOENCODING = "utf-8"
& $Python (Join-Path $ProjectRoot "src\main.py")
