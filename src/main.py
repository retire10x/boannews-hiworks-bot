import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser

HIWORKS_SMTP_USER = os.getenv("HIWORKS_SMTP_USER")
HIWORKS_SMTP_PASS = os.getenv("HIWORKS_SMTP_PASS")
TARGET_EMAIL = os.getenv("TARGET_EMAIL")

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


def send_rss_email(title, link, description, pub_date):
    if not all([HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS, TARGET_EMAIL]):
        raise RuntimeError(
            "HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS, TARGET_EMAIL 환경 변수가 필요합니다."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[보안뉴스] {title}"
    msg["From"] = HIWORKS_SMTP_USER
    msg["To"] = TARGET_EMAIL

    html_content = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0056b3;"><a href="{link}" target="_blank" style="text-decoration: none; color: #0056b3;">{title}</a></h2>
        <p style="color: #888; font-size: 13px;">발행일시: {pub_date}</p>
        <hr style="border: 0; border-top: 1px solid #eee;">
        <p style="font-size: 14px; color: #444;">{description}</p>
        <br>
        <p><a href="{link}" target="_blank" style="background-color: #007bff; color: white; padding: 8px 14px; text-decoration: none; border-radius: 4px; display: inline-block;">원문 기사 읽기</a></p>
    </div>
    """

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtps.hiworks.com", 465) as server:
        server.login(HIWORKS_SMTP_USER, HIWORKS_SMTP_PASS)
        server.sendmail(HIWORKS_SMTP_USER, [TARGET_EMAIL], msg.as_string())


def process_rss():
    feed = feedparser.parse(RSS_URL)
    if feed.bozo and not feed.entries:
        print(f"RSS 파싱 오류: {feed.bozo_exception}")
        return

    history = load_history()
    new_history = set(history)

    for entry in reversed(feed.entries):
        article_id = entry.get("link") or entry.get("title")
        if not article_id or article_id in history:
            continue

        title = entry.title
        link = entry.link
        description = entry.get("description", "")
        pub_date = entry.get("published", "")

        try:
            send_rss_email(title, link, description, pub_date)
            print(f"발송 완료: {title}")
            new_history.add(article_id)
        except Exception as e:
            print(f"발송 실패 ({title}): {e}")

    save_history(new_history)


if __name__ == "__main__":
    process_rss()
