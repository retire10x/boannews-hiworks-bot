"""POP3 받은편지함 제목 샘플 (디버그). 비밀번호는 출력하지 않음."""
import os
import poplib
import sys
from datetime import datetime

from email import message_from_bytes
from email.header import decode_header

from env_loader import load_project_env


def decode_subj(value: str | None) -> str:
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


def main() -> None:
    load_project_env()
    user = (os.getenv("HIWORKS_SMTP_USER") or "").strip()
    password = (os.getenv("HIWORKS_SMTP_PASS") or "").strip()
    if not user or not password:
        print("HIWORKS_SMTP_USER/PASS 필요", file=sys.stderr)
        sys.exit(1)

    limit = 15
    if "--all" in sys.argv:
        limit = 9999

    pop = poplib.POP3_SSL("pop3s.hiworks.com", 995, timeout=30)
    try:
        pop.user(user)
        pop.pass_(password)
        stat = pop.stat()
        print(f"POP3 stat: {stat[0]} messages, {stat[1]} bytes")
        _, listings, _ = pop.uidl()
        nums = []
        for line in listings:
            if not line:
                continue
            parts = line.decode("utf-8", errors="replace").split()
            if len(parts) >= 2:
                nums.append((int(parts[0]), parts[1]))
        nums.sort(key=lambda x: x[0], reverse=True)
        print(f"최근 {min(limit, len(nums))}통 제목 (번호 큰 쪽=최근):")
        tag = "[보안뉴스]"
        match = 0
        for msg_num, uid in nums[:limit]:
            _, raw_lines, _ = pop.retr(msg_num)
            raw = b"\n".join(raw_lines)
            msg = message_from_bytes(raw)
            subj = decode_subj(msg.get("Subject"))
            date = msg.get("Date") or ""
            hit = tag in subj
            if hit:
                match += 1
            mark = " *" if hit else ""
            print(f"  #{msg_num} uid={uid}{mark}")
            print(f"      Subject: {subj}")
            print(f"      Date: {date}")
        print(f"\n제목에 '{tag}' 포함: {match}통 (표본 {min(limit, len(nums))}통 중)")
    finally:
        try:
            pop.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
