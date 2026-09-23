# Playwright 하이웍스 프로필 삭제 → OTP 로그인을 처음부터 다시
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "ensure_utf8.ps1")

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Profile = Join-Path $ProjectRoot ".hiworks_browser_profile"

if (Test-Path $Profile) {
    Remove-Item -LiteralPath $Profile -Recurse -Force
    Write-Host "삭제함: $Profile"
} else {
    Write-Host "프로필 없음 (이미 초기 상태): $Profile"
}

Write-Host ""
Write-Host "다음: .\scripts\run_board_poster.ps1"
Write-Host "  → 스크립트가 연 Chromium 창에서 ID / 비밀번호 / OTP 를 입력하세요."
