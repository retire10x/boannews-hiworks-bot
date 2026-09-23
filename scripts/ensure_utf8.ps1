# Windows PowerShell / 작업 스케줄러에서 한글·Python UTF-8 출력용 (dot-source)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
    if ($Host.Name -eq "ConsoleHost") {
        chcp 65001 | Out-Null
    }
} catch {
    # ignore
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
[Console]::InputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
