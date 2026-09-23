import poplib
import re
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from typing import Optional


@dataclass
class InboundMail:
    pop_uid: str
    subject: str
    text_body: str
    html_body: str


def _decode_header(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _extract_bodies(msg: Message) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(decoded)
            else:
                text_parts.append(decoded)
    return "\n".join(text_parts).strip(), "\n".join(html_parts).strip()


def _html_to_plain(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_security_news_mails(
    user: str,
    password: str,
    subject_tag: str = "[보안뉴스]",
    host: str = "pop3s.hiworks.com",
    port: int = 995,
) -> list[InboundMail]:
    pop = poplib.POP3_SSL(host, port, timeout=30)
    try:
        pop.user(user)
        pop.pass_(password)
        _, listings, _ = pop.uidl()
        results: list[InboundMail] = []
        for line in listings:
            if not line:
                continue
            parts = line.decode("utf-8", errors="replace").split()
            if len(parts) < 2:
                continue
            msg_num, uid = parts[0], parts[1]
            _, raw_lines, _ = pop.retr(int(msg_num))
            raw = b"\n".join(raw_lines)
            msg = message_from_bytes(raw)
            subject = _decode_header(msg.get("Subject"))
            if subject_tag not in subject:
                continue
            text_body, html_body = _extract_bodies(msg)
            if not text_body and html_body:
                text_body = _html_to_plain(html_body)
            results.append(
                InboundMail(
                    pop_uid=uid,
                    subject=subject.strip(),
                    text_body=text_body,
                    html_body=html_body,
                )
            )
        return results
    finally:
        try:
            pop.quit()
        except Exception:
            pass
