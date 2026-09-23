# 게시판 글쓰기 화면 확인 (브라우저 표시, OTP 가능)
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "ensure_utf8.ps1")

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot
$env:HIWORKS_PLAYWRIGHT_HEADLESS = "0"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
& $Python -u (Join-Path $ProjectRoot "src\debug_board_editor.py") @args
