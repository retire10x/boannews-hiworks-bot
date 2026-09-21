# boannews-hiworks-bot

보안뉴스(Boannews) RSS를 주기적으로 확인하고, 새 기사를 하이웍스 SMTP로 메일 발송합니다.  
하이웍스 **메일 자동 분류(규칙)** 에서 「수신 메일을 게시판으로 등록」을 설정해 두면 OTP 없이 전사 게시판까지 자동 등록됩니다.

## 동작 흐름

1. GitHub Actions(매시 정각, UTC)가 RSS를 조회합니다.
2. 미발송 기사만 `[보안뉴스]` 제목으로 SMTP 발송합니다.
3. 하이웍스 메일함에서 규칙이 게시판에 글을 등록합니다.

## 하이웍스 메일 규칙 (수동 1회)

- **조건**: 제목에 `[보안뉴스]` 포함 (또는 발신 주소 = SMTP 발신 계정)
- **동작**: 게시판으로 등록 → 대상 게시판 선택

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env     # 값 입력 후
python src/main.py
```

## GitHub Secrets

**Repository secrets**에 아래 **이름 그대로** 3개를 등록해야 합니다 (`.env`와 별개).

| Secret | 설명 |
|--------|------|
| `HIWORKS_SMTP_USER` | 발신 하이웍스 메일 |
| `HIWORKS_SMTP_PASS` | **메일 전용 비밀번호** (OTP 사용 시 로그인 비밀번호 불가) |
| `TARGET_EMAIL` | 규칙이 걸린 수신 메일 주소 |

다른 이름(예: `HIWORKSCTRL`)으로 넣으면 워크플로에서 읽지 못합니다.

메일 전용 비밀번호: 웹메일 **메일 프로그램 환경 설정 안내** 또는 **내 정보 → 설정 → 보안 설정**

## SMTP (하이웍스 공식 연동 값)

| 항목 | 값 |
|------|-----|
| 아이디 | 전체 주소 → `HIWORKS_SMTP_USER` |
| 비밀번호 | 메일 전용 비밀번호 → `HIWORKS_SMTP_PASS` |
| SMTP | `smtps.hiworks.com` / **465** / SSL |

POP3/SMTP: **환경설정 → 기본 설정 → 사용 함** 필수.

## Windows 작업 스케줄러 (운영 권장)

GitHub Actions는 하이웍스 **허용 국가(대한민국)** 와 맞지 않을 수 있습니다.  
**매일 같은 시각 1회** 실행은 작업 스케줄러 + `scripts/run_rss_mailer.ps1` 을 사용하세요.

단계별 가이드: [docs/windows-task-scheduler.md](docs/windows-task-scheduler.md)

## 수동 워크플로 실행 (GitHub, 선택)

GitHub → Actions → **Boannews RSS to Hiworks Board via Email Filter** → **Run workflow**
