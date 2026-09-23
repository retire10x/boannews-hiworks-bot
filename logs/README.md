# 실행 로그 (에이전트 / 디버그)

`.\scripts\run_board_poster.ps1` 실행 시 터미널과 **동일한 출력**이 여기에 기록됩니다.  
Cursor 에이전트는 통합 터미널 파일을 못 읽는 경우가 많으므로, **실패·성공 분석은 아래 파일을 우선** 엽니다.

| 파일 | 설명 |
|------|------|
| `board_poster_last_run.log` | 가장 최근 1회 전체 stdout/stderr |
| `board_poster_last_run.meta.json` | 종료 코드, 시작·종료 시각, 소요 시간(초) |
| `board_poster.log` | 누적 이력 |

자세한 안내: 프로젝트 루트 `AGENTS.md`
