# PC 전용: 수신 메일 -> 게시판 등록 (세션 없으면 Playwright 로그인 창)
param(
    [switch]$Scheduled
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "ensure_utf8.ps1")

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "run_logging.ps1") -ProjectRoot $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-RunLog "오류: .venv 없음. python -m venv .venv; pip install -r requirements.txt; playwright install chromium"
    Write-RunLogMeta -ExitCode 1
    exit 1
}

$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-RunLog "오류: .env 없음 ($EnvFile)"
    Write-RunLogMeta -ExitCode 1
    exit 1
}

$Poster = Join-Path $ProjectRoot "src\post_board_from_mail.py"

if ($Scheduled) {
    $env:HIWORKS_SCHEDULED = "1"
} else {
    Remove-Item Env:HIWORKS_SCHEDULED -ErrorAction SilentlyContinue
}

$env:HIWORKS_RUN_LOG = $script:RunLogLast

Write-RunLog "=== board poster 시작 (Scheduled=$Scheduled) ==="
Write-RunLog "  (로그 파일: logs\board_poster_last_run.log)"

function Invoke-Poster {
    param([string[]]$ExtraArgs = @())
    Invoke-PythonWithRunLog -PythonExe $Python -Arguments (@("-u", $Poster) + $ExtraArgs)
}

$code = Invoke-Poster
if ($code -eq 2) {
    if ($Scheduled -or $env:HIWORKS_SCHEDULED -eq "1") {
        Write-RunLog "하이웍스 로그인 세션 없음. 스케줄러 모드에서는 브라우저 로그인을 건너뜁니다."
        Write-RunLog "  PC 로그인 상태에서 수동 실행: .\scripts\run_board_poster.ps1"
        Write-RunLog "  또는: python src\setup_hiworks_browser.py"
        Write-RunLogMeta -ExitCode 2
        exit 2
    }
    Write-RunLog "=== 세션 없음. 브라우저에서 OTP 로그인하면 자동으로 게시까지 진행합니다. ==="
    $code = Invoke-Poster
}

Write-RunLog "=== 종료 코드: $code ==="
Write-RunLogMeta -ExitCode $code
exit $code
