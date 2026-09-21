"""하이웍스 POP3/SMTP 인증만 검사 (메일 발송·RSS 없음)."""
import os
import poplib
import smtplib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8-sig")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ[key] = value


try:
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=True)
except ImportError:
    pass

load_env_file(ENV_FILE)


def _fmt_err(exc: BaseException) -> str:
    if isinstance(exc, smtplib.SMTPException) and exc.args:
        return str(exc.args[0])
    return str(exc)


def test_pop3(user: str, password: str) -> bool:
    try:
        pop = poplib.POP3_SSL("pop3s.hiworks.com", 995, timeout=25)
        pop.user(user)
        pop.pass_(password)
        pop.quit()
        print("POP3 로그인: OK")
        return True
    except BaseException as exc:
        print(f"POP3 로그인: FAIL — {_fmt_err(exc)}")
        return False


def test_smtp(user: str, password: str) -> bool:
    smtp = None
    try:
        smtp = smtplib.SMTP_SSL("smtps.hiworks.com", 465, timeout=25)
        smtp.login(user, password)
        print("SMTP 로그인: OK")
        return True
    except BaseException as exc:
        print(f"SMTP 로그인: FAIL — {_fmt_err(exc)}")
        return False
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass


def main() -> int:
    user = (os.getenv("HIWORKS_SMTP_USER") or "").strip()
    password = (os.getenv("HIWORKS_SMTP_PASS") or "").strip()

    if not user or not password:
        print("HIWORKS_SMTP_USER / HIWORKS_SMTP_PASS 가 .env 에 없습니다.")
        return 1

    print(f"계정: {user}")
    print(f"비밀번호 길이: {len(password)} (메일 전용 비밀번호를 그대로 복사했는지 확인)")

    pop3_ok = test_pop3(user, password)
    smtp_ok = test_smtp(user, password)

    if pop3_ok and smtp_ok:
        print("\n인증 OK — python src/main.py 로 RSS 발송 테스트 가능")
        return 0

    print(
        "\n인증 실패 — 아래를 순서대로 확인하세요:\n"
        "  1) 웹메일에 admin@hnkkorea.com 으로 로그인한 뒤 POP3/SMTP [사용 함] 저장\n"
        "  2) 허용 국가 → 대한민국\n"
        "  3) [메일 전용 비밀번호] 재발급 → .env HIWORKS_SMTP_PASS 즉시 반영\n"
        "  4) 아웃룩에 동일 계정·서버(pop3s/smtps.hiworks.com)로 수동 추가 테스트\n"
        "  5) admin@ 공용/관리 계정은 POP3/SMTP가 막혀 있을 수 있음 → IT 문의\n"
        "  6) 우회: 아웃룩 되는 개인 @hnkkorea.com 으로 발송, 규칙은 제목 [보안뉴스]만"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
