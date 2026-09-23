# PC: 수신 메일 → 게시판 자동 등록

**서버**는 `run_rss_mailer.ps1` 로 digest 메일만 발송합니다.  
**본인 PC**에서 `[보안뉴스]` 메일을 **웹메일(ERP자동메일 등)** 에서 찾고, **본문을 읽어** **정보보안 뉴스레터 게시판 글쓰기 URL**에 제목·본문을 넣어 등록합니다 (`board_form`).

> 하이웍스 **POP3는 받은편지함만** 가져옵니다. 메일 규칙으로 **개인편지함**(예: ERP자동메일)으로 옮기면 POP3로는 보이지 않습니다.  
> 그 경우 `HIWORKS_MAIL_LIST_URL` 에 [웹메일 목록 URL](https://mails.office.hiworks.com/list/personal/717?page=1) 을 넣고 `HIWORKS_MAIL_FETCH=web` 으로 설정하세요.

## 1. PC `.env` 추가 항목

```env
# POP3는 SMTP와 동일 계정·메일 전용 비밀번호 (이미 있으면 생략 가능)
HIWORKS_SMTP_USER=jsh38@hnkkorea.com
HIWORKS_SMTP_PASS="..."

# 오피스 로그인 페이지 (회사 도메인)
HIWORKS_OFFICE_HOME=https://login.office.hiworks.com/hnkkorea.com

HIWORKS_POST_METHOD=board_form
HIWORKS_BOARD_WRITE_URL=https://boards.office.hiworks.com/board/postwrite/normal/328/new

# UI가 다르면 (선택)
# HIWORKS_BOARD_SELECTOR_TITLE=
# HIWORKS_BOARD_SELECTOR_BODY=
# HIWORKS_BOARD_SELECTOR_SUBMIT=
# HIWORKS_PLAYWRIGHT_HEADLESS=0
# HIWORKS_PLAYWRIGHT_USER_DATA_DIR=.hiworks_browser_profile

# digest가 개인편지함으로 분류될 때 (717 = ERP자동메일 예시)
HIWORKS_MAIL_FETCH=web
HIWORKS_MAIL_LIST_URL=https://mails.office.hiworks.com/list/personal/717?page=1
# 받은편지함만 쓸 때: https://mails.office.hiworks.com/list/inbox?page=1
```

## 2. PC 1회 설치

```powershell
cd D:\develop\hiworks-Ctrl
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\playwright install chromium
```

## 3. 아침 OTP 로그인 (1회 / 세션 유지)

```powershell
python src/setup_hiworks_browser.py
```

브라우저가 열리면 **OTP 로그인**만 하면 됩니다. 편지함이 보이면 **자동으로** 게시까지 진행합니다 (Enter 불필요).

### 하이웍스 **메신저**로만 로그인해 있는 경우

- **메신저 앱 로그인 ≠ 이 스크립트용 브라우저 로그인** 입니다.  
  Playwright는 프로젝트 폴더의 **`.hiworks_browser_profile`** (별도 Chromium)만 사용합니다.
- [login.office.hiworks.com/hnkkorea.com](https://login.office.hiworks.com/hnkkorea.com) 이 **로그인 화면**으로 나오는 것은 **정상**입니다.  
  `setup_hiworks_browser.py` 가 연 **그 창에서** ID·비밀번호·OTP를 **한 번** 입력하면, 이후 `post_board_from_mail.py` 가 그 세션을 재사용합니다.
- 메일은 메신저/아웃룩으로 보셔도 됩니다. **게시판 자동 등록**만 위 브라우저 프로필 로그인이 필요합니다.

## 4. 편지함 URL

1. 하이웍스 **웹메일** → digest가 모이는 편지함(예: **ERP자동메일**)
2. 주소창 URL을 `HIWORKS_MAIL_LIST_URL` 에 넣기 (예: `.../list/personal/717?page=1`)

## 5. 테스트

```powershell
# 등록 대상 메일만 목록 (게시 안 함)
python src/post_board_from_mail.py --dry-run

# 실제 게시 (로그인 세션 필요)
.\scripts\run_board_poster.ps1
```

처리한 메일 식별자(메일 URL)는 `board_posted_uids.txt` 에 저장되어 **중복 게시하지 않습니다**.

**처음 실행 시** 편지함에 예전 `[보안뉴스]` 가 많으면 `--dry-run` 으로 대상 확인 후,  
이미 처리한 메일을 `board_posted_uids.txt` 에 넣거나 메일함을 정리하세요.

## 6. PC 작업 스케줄러 — **10시 / 14시 / 18시** (하루 3회)

서버에서 digest 메일 발송 후, PC에서 **메일 확인 + 게시**를 3번 시도합니다.  
세션이 없으면 `run_board_poster.ps1` 이 **Playwright 로그인 창**을 띄웁니다. (그때 PC 앞에서 ID·비밀번호·OTP만 입력하면 이후 자동으로 이어서 진행됩니다)

### 6-1. 작업 스케줄러 열기

`Win + R` → `taskschd.msc`

### 6-2. 작업 만들기

| 일반 | 이름: `Boannews PC Board Poster` |
| | **사용자가 로그온할 때만 실행** (Playwright 창·OTP용 — **「로그온 여부에 관계없이」는 사용 금지**) |

### 6-3. 트리거 **3개** (각각 새로 만들기)

| # | 설정 | 시작 시간 |
|---|------|-----------|
| 1 | 매일 | **10:00:00** |
| 2 | 매일 | **14:00:00** |
| 3 | 매일 | **18:00:00** |

### 6-4. 동작

| 항목 | 값 |
|------|-----|
| 프로그램 | `powershell.exe` |
| 인수 | `-NoProfile -ExecutionPolicy Bypass -File "D:\develop\hiworks-Ctrl\scripts\run_board_poster.ps1" -Scheduled` |
| 시작 위치 | `D:\develop\hiworks-Ctrl` |

(경로는 PC 실제 폴더로 변경)

### 6-5. 설정 탭

- **새 인스턴스 실행 안 함**
- **요청 시 작업 실행 허용** (수동 테스트용)

### 6-6. 동작 요약

```
10:00 / 14:00 / 18:00
  → run_board_poster.ps1
  → 새 [보안뉴스] 메일 있으면 게시
  → 세션 없음(exit 2, -Scheduled 모드) → 로그인 대기 없이 종료, 수동 실행 필요
```

**주의:** 스케줄 시각에 세션이 만료돼 있으면 **브라우저 창에서 직접 로그인**해야 합니다(스케줄러 모드는 무한 대기하지 않고 종료). 10시 전에 한 번 로그인해 두면 14·18시는 세션만으로 될 수 있습니다.

### 6-7. 「실행 중」인데 아무 일도 안 보일 때

1. **로그 파일** — 최근 1회: `logs\board_poster_last_run.log` · 누적: `logs\board_poster.log` · 메타: `logs\board_poster_last_run.meta.json`  
   - `게시할 새 [보안뉴스] 메일 없음` → **정상 종료** (브라우저 안 뜸). digest가 아직 없거나 이미 `board_posted_uids.txt` 에 기록됨.  
   - `웹메일 편지함 준비됨` 이 뜨지 않고 오래 멈춤 → 네트워크 지연이거나 하이웍스 페이지 구조 변경 가능성.  
   - `로그인 세션 없음` + `-Scheduled` → OTP 없이 종료(exit 2). **수동으로** `setup_hiworks_browser.py` 실행.
2. **작업 스케줄러 일반 탭** — **「사용자가 로그온할 때만 실행」** 인지 확인.
3. **동작 인수** — 반드시 `-Scheduled` 포함 (세션 없을 때 로그인 대기 없이 즉시 종료하게 함).
4. **수동 테스트** — PowerShell에서 `.\scripts\run_board_poster.ps1` 실행해 메시지 확인.

## 7. 로그인 만료 시

`post_board_from_mail.py` 가 **로그인 세션 없음** 으로 종료되면:

```powershell
python src/setup_hiworks_browser.py
```

다시 OTP 1회 입력.
