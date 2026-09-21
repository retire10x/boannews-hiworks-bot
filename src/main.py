import html
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_env_file(path: Path) -> None:
    """`.env`를 읽어 os.environ에 넣습니다 (dotenv 미설치 시에도 동작)."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8-sig")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


try:
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=True)
except ImportError:
    pass

load_env_file(ENV_FILE)

HIWORKS_SMTP_USER = (os.getenv("HIWORKS_SMTP_USER") or "").strip()
HIWORKS_SMTP_PASS = (os.getenv("HIWORKS_SMTP_PASS") or "").strip()
TARGET_EMAIL = (os.getenv("TARGET_EMAIL") or "").strip()

RSS_URL = "https://www.boannews.com/rss/clickTop.xml"
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "published_history.txt",
)


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    return set()


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for item_id in sorted(history):
            f.write(f"{item_id}\n")


def collect_new_entries(feed, history):
    new_entries = []
    for entry in reversed(feed.entries):
        article_id = entry.get("link") or entry.get("title")
        if not article_id or article_id in history:
            continue
        new_entries.append(
            {
                "id": article_id,
                "title": entry.title,
                "link": entry.link,
                "description": entry.get("description", ""),
                "pub_date": entry.get("published", ""),
            }
        )
    return new_entries


def build_digest_html(entries):
    blocks = []
    for i, item in enumerate(entries, start=1):
        title = html.escape(item["title"])
        link = html.escape(item["link"], quote=True)
        desc = html.escape(item["description"])
        pub = html.escape(item["pub_date"])
        blocks.append(
            f"""
        <div style="margin-bottom: 28px; padding-bottom: 20px; border-bottom: 1px solid #eee;">
            <h3 style="margin: 0 0 8px; color: #0056b3; font-size: 16px;">
                {i}. <a href="{link}" target="_blank" style="color: #0056b3; text-decoration: none;">{title}</a>
            </h3>
            <p style="margin: 0 0 8px; color: #888; font-size: 12px;">발행: {pub}</p>
            <p style="margin: 0 0 10px; font-size: 14px; color: #444;">{desc}</p>
            <a href="{link}" target="_blank" style="font-size: 13px;">원문 보기</a>
        </div>
        """
        )
    return "\n".join(blocks)


def send_digest_email(entries):
    if not all([HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS, TARGET_EMAIL]):
        raise RuntimeError(
            "HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS, TARGET_EMAIL 환경 변수가 필요합니다."
        )

    n = len(entries)
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[보안뉴스] 신규 {n}건 ({today})"
    msg["From"] = HIWORKS_SMTP_USER
    msg["To"] = TARGET_EMAIL

    body = build_digest_html(entries)
    html_content = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 720px;">
        <h2 style="color: #0056b3; margin-bottom: 4px;">Boannews 보안뉴스 요약</h2>
        <p style="color: #666; font-size: 13px; margin-top: 0;">신규 기사 {n}건</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 16px 0;">
        {body}
    </div>
    """
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtps.hiworks.com", 465) as server:
        server.login(HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS)
        server.sendmail(HIWORKS_SMTP_USER, [TARGET_EMAIL], msg.as_string())


def validate_env():
    fields = {
        "HIWORKS_SMTP_USER": HIWORKS_SMTP_USER,
        "HIWORKS_SMTP_PASS": HIWORKS_SMTP_PASS,
        "TARGET_EMAIL": TARGET_EMAIL,
    }
    missing = [name for name, val in fields.items() if not val]
    if not missing:
        return

    print("오류: 다음 환경 변수가 비어 있습니다:", ", ".join(missing))
    print(f"  .env 경로: {ENV_FILE}")
    print(f"  .env 파일 존재: {ENV_FILE.is_file()}")
    if ENV_FILE.is_file():
        print("  → .env 저장(Ctrl+S) 및 HIWORKS_SMTP_PASS(메일 전용 비밀번호) 확인")
    else:
        print("  → .env.example 을 복사해 .env 생성 후 값 입력")
    print("  (GitHub 와 무관. 이 폴더의 .env 만 사용합니다.)")
    sys.exit(1)


def process_rss():
    validate_env()

    feed = feedparser.parse(RSS_URL)
    if feed.bozo and not feed.entries:
        print(f"RSS 파싱 오류: {feed.bozo_exception}")
        sys.exit(1)

    history = load_history()
    new_entries = collect_new_entries(feed, history)

    if not new_entries:
        print("신규 기사 없음 — 발송 생략")
        return

    try:
        send_digest_email(new_entries)
    except Exception as e:
        print(f"발송 실패: {e}")
        sys.exit(1)

    for item in new_entries:
        print(f"  - {item['title']}")
    print(f"발송 완료: [보안뉴스] 신규 {len(new_entries)}건 (메일 1통)")

    new_history = set(history)
    for item in new_entries:
        new_history.add(item["id"])
    save_history(new_history)


if __name__ == "__main__":
    process_rss()
