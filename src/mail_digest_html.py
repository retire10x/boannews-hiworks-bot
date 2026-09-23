"""digest 메일 HTML → 게시판 SmartEditor용 본문."""
import re


def sanitize_digest_html(html: str) -> str:
    """
    메일 iframe 전체 문서에서 Boannews digest 블록만 남김 (script·head 제거).
    """
    raw = (html or "").strip()
    if not raw:
        return ""

    raw = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", raw, flags=re.I)
    body_m = re.search(r"<body[^>]*>([\s\S]*?)</body>", raw, flags=re.I)
    if body_m:
        raw = body_m.group(1)

    raw = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", raw, flags=re.I)

    if "Boannews" in raw:
        idx = raw.find("Boannews")
        div_start = raw.rfind("<div", 0, idx)
        if div_start >= 0:
            raw = raw[div_start:]
            raw = re.sub(r"</body>[\s\S]*$", "", raw, flags=re.I)
            raw = re.sub(r"</html>[\s\S]*$", "", raw, flags=re.I)

    raw = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", raw, flags=re.I)
    return raw.strip()
