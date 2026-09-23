# run_board_poster 등 — 터미널 출력을 logs/ 에 남겨 Cursor/에이전트가 읽을 수 있게 함 (dot-source)
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$script:RunLogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $script:RunLogDir | Out-Null

$script:RunLogAppend = Join-Path $script:RunLogDir "board_poster.log"
$script:RunLogLast = Join-Path $script:RunLogDir "board_poster_last_run.log"
$script:RunLogMeta = Join-Path $script:RunLogDir "board_poster_last_run.meta.json"
$script:RunLogUtf8 = New-Object System.Text.UTF8Encoding $false
$script:RunStartedAt = Get-Date

[System.IO.File]::WriteAllText($script:RunLogLast, "", $script:RunLogUtf8)

function Write-RunLog {
    param([string]$Message)
    $line = if ($Message -match '^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]') {
        $Message
    } else {
        "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    }
    [System.IO.File]::AppendAllText($script:RunLogAppend, $line + [Environment]::NewLine, $script:RunLogUtf8)
    [System.IO.File]::AppendAllText($script:RunLogLast, $line + [Environment]::NewLine, $script:RunLogUtf8)
    Write-Host $Message
}

function Write-RunLogBlock {
    param([object[]]$Lines)
    foreach ($item in $Lines) {
        $text = if ($item -is [System.Management.Automation.ErrorRecord]) {
            $item.ToString()
        } else {
            "$item"
        }
        if ($text -match "`n") {
            foreach ($sub in $text -split "`n") {
                if ($sub.Trim().Length -gt 0) { Write-RunLog $sub }
            }
        } else {
            Write-RunLog $text
        }
    }
}

function Invoke-PythonWithRunLog {
    param(
        [string]$PythonExe,
        [string[]]$Arguments
    )
    # 파이프로 스트리밍: 프로세스가 끝나야만 한꺼번에 기록되던 문제를 없애고,
    # 실행 중에도 에이전트/사용자가 진행 상황을 로그 파일에서 실시간으로 볼 수 있게 함.
    & $PythonExe @Arguments 2>&1 | ForEach-Object {
        Write-RunLogBlock -Lines @($_)
    }
    $code = $LASTEXITCODE
    return [int]$code
}

function Write-RunLogMeta {
    param(
        [int]$ExitCode,
        [string]$Label = "board_poster"
    )
    $ended = Get-Date
    $meta = @{
        label      = $Label
        exit_code  = $ExitCode
        started_at = $script:RunStartedAt.ToString("yyyy-MM-dd HH:mm:ss")
        ended_at   = $ended.ToString("yyyy-MM-dd HH:mm:ss")
        duration_sec = [int]($ended - $script:RunStartedAt).TotalSeconds
        last_run_log = $script:RunLogLast
        append_log   = $script:RunLogAppend
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($script:RunLogMeta, $meta, $script:RunLogUtf8)
}
