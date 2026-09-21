import html
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass

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
    if not all([HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS, TARGET_EMAIL]):
        print(
            "오류: HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS, TARGET_EMAIL 이 비어 있습니다. "
            "GitHub Repository Secrets 이름이 정확히 일치하는지 확인하세요."
        )
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
