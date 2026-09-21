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

| Secret | 설명 |
|--------|------|
| `HIWORKS_SMTP_USER` | 발신 하이웍스 메일 |
| `HIWORKS_SMTP_PASS` | 비밀번호 또는 **앱 비밀번호** (OTP 사용 시 필수) |
| `TARGET_EMAIL` | 규칙이 걸린 수신 메일 주소 |

앱 비밀번호: 하이웍스 오피스 → 프로필 → 보안 설정 → 앱 비밀번호 생성

## SMTP

- 호스트: `smtps.hiworks.com`
- 포트: `465` (SSL)

## 수동 워크플로 실행

GitHub → Actions → **Boannews RSS to Hiworks Board via Email Filter** → **Run workflow**
