# 에이전트 / Cursor 참고

## board poster 실행 로그 (터미널 대신 여기를 읽을 것)

PowerShell 터미널 버퍼는 세션마다 달라 IDE 에이전트가 항상 읽지 못할 수 있다.  
`run_board_poster.ps1` 은 **동일 내용**을 파일로 남긴다.

| 파일 | 용도 |
|------|------|
| `logs/board_poster_last_run.log` | **가장 최근 1회** 실행 전체 stdout/stderr |
| `logs/board_poster_last_run.meta.json` | 종료 코드, 시작·종료 시각, duration |
| `logs/board_poster.log` | 누적 이력 |

문제 분석 시 우선 `board_poster_last_run.log` 와 `.meta.json` 을 연다.

## 수동 확인

```powershell
Get-Content .\logs\board_poster_last_run.log -Tail 80 -Encoding utf8
Get-Content .\logs\board_poster_last_run.meta.json -Encoding utf8
```
