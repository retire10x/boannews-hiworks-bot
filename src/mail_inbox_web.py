"""하이웍스 웹메일 목록에서 [보안뉴스] 메일 수집 (개인 편지함 등 POP3 미포함함)."""
import os
import re
import sys
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from typing import Callable

from hiworks_board import (
    _profile_dir,
    attach_dialog_auto_dismiss,
    try_prefill_login_id,
)
from hiworks_session import (
    ensure_mail_session_or_exit,
    needs_login,
    wait_for_mail_read_ui,
    wait_for_mail_ui,
    wait_until_mail_session,
)
from mail_digest_html import sanitize_digest_html
from playwright_iframe import iframe_frame
from mail_inbox import InboundMail

MAIL_ORIGIN = "https://mails.office.hiworks.com"
# 하이웍스 웹메일 HTML 본문 iframe (ID가 환경마다 동일한 경우가 많음)
DEFAULT_MAIL_BODY_IFRAME = "#viewContentIframeId"


def _normalize_mail_url(href: str, base: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return ""
    return urljoin(base, href)


_DIGEST_MARKERS = ("Boannews", "보안뉴스 요약", "원문 보기", "신규 기사")

_MAIL_CHROME_MARKERS = (
    "상단메뉴 바로가기",
    "상단 메뉴",
    "왼쪽메뉴 바로가기",
    "왼쪽 메뉴",
    "본문영역 바로가기",
    "본문 영역",
    "전체 편지함",
    "전체 메일함",
    "받은편지함",
    "받은 메일함",
    "보낸편지함",
    "보낸 메일함",
    "읽음 확인",
    "수신확인",
    "스팸 편지함",
    "스팸 메일함",
    "다른 작업",
    "메일 설정",
    "메일 환경설정",
    "메일 쓰기",
    "하이웍스 메일",
    "임시보관함",
    "개인 메일함",
    "휴지통",
)

_CHROME_LINE_RE = re.compile(
    r"바로가기|편지함|메일함|메일\s*쓰기|메일\s*환경설정|메일\s*설정|"
    r"다른\s*작업|답장|전체답장|전달|하이웍스\s*메일|AI요약|번역|"
    r"SMTP\s*인증|읽은\s*사람",
    re.I,
)


def _mail_chrome_score(text: str) -> int:
    return sum(1 for m in _MAIL_CHROME_MARKERS if m in (text or ""))


def _normalize_body_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    return text[:12000]


def _anchor_digest_text(text: str) -> str:
    for marker in _DIGEST_MARKERS:
        idx = (text or "").find(marker)
        if idx >= 0:
            return (text[idx:]).strip()
    return (text or "").strip()


def _trim_leading_mail_chrome(text: str) -> str:
    """페이지 전체 텍스트 fallback 시 앞쪽 UI·헤더 줄 제거."""
    anchored = _anchor_digest_text(text)
    if anchored != (text or "").strip() and len(anchored) > 80:
        return _normalize_body_text(anchored)

    lines = [(ln or "").strip() for ln in (text or "").splitlines()]
    out: list[str] = []
    skipped_header = False
    for line in lines:
        if not line:
            if out:
                out.append("")
            continue
        if any(m in line for m in _MAIL_CHROME_MARKERS) or _CHROME_LINE_RE.search(line):
            continue
        if re.match(r"^(보낸\s*사람|받는\s*사람|참조|제목)\s*[:：]", line):
            skipped_header = True
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", line) and skipped_header:
            continue
        if line in ("답장", "전체답장", "전달", "삭제", "이동", "인쇄"):
            continue
        out.append(line)
    joined = _normalize_body_text("\n".join(out))
    if joined:
        return joined
    return _normalize_body_text(_anchor_digest_text(text))


def _wait_for_view_content_iframe(page, iframe_sel: str, timeout_ms: int = 30_000) -> None:
    page.locator(iframe_sel).first.wait_for(state="attached", timeout=timeout_ms)
    page.wait_for_function(
        """(sel) => {
            const f = document.querySelector(sel);
            if (!f) return false;
            try {
              const t = (f.contentDocument?.body?.innerText || '').trim();
              return t.length > 20;
            } catch (e) { return false; }
        }""",
        arg=iframe_sel,
        timeout=timeout_ms,
    )


def _wait_for_digest_in_mail_iframe(page, timeout_ms: int = 30_000) -> None:
    iframe_sel = (
        (os.getenv("HIWORKS_MAIL_BODY_IFRAME") or "").strip() or DEFAULT_MAIL_BODY_IFRAME
    )
    try:
        _wait_for_view_content_iframe(page, iframe_sel, timeout_ms=timeout_ms)
        return
    except PlaywrightTimeout:
        pass
    page.wait_for_function(
        """() => {
            for (const f of document.querySelectorAll('iframe')) {
              try {
                const t = f.contentDocument?.body?.innerText || '';
                if (t.includes('Boannews') || t.includes('원문 보기')) return true;
              } catch (e) {}
            }
            return false;
        }""",
        timeout=min(timeout_ms, 15_000),
    )


def _looks_like_boannews_digest(text: str, html: str) -> bool:
    blob = (text or "") + (html or "")
    return "Boannews" in blob or "원문 보기" in blob


def _extract_view_content_iframe(page, iframe_sel: str) -> tuple[str, str] | None:
    loc = page.locator(iframe_sel).first
    try:
        loc.wait_for(state="attached", timeout=20_000)
    except PlaywrightTimeout:
        return None

    inner = (os.getenv("HIWORKS_MAIL_BODY_INNER_SELECTOR") or "body").strip() or "body"
    for _ in range(40):
        frame = iframe_frame(loc, timeout_ms=5000)
        if frame:
            try:
                html_raw = frame.evaluate(
                    """() => {
                    document.querySelectorAll('script').forEach(s => s.remove());
                    const h2 = [...document.querySelectorAll('h2')].find(
                      el => (el.textContent || '').includes('Boannews')
                    );
                    const root = h2 && (
                      h2.closest('div[style*="max-width"]') || h2.closest('div')
                    );
                    if (root) return root.outerHTML;
                    return document.body ? document.body.innerHTML : '';
                  }"""
                ) or ""
                html = sanitize_digest_html(html_raw)
                text = _normalize_body_text(
                    frame.locator(inner).inner_text(timeout=4000) or ""
                )
                if len(text) > 25 or len(html) > 60:
                    return text, html
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def _extract_via_configured_mail_body(page) -> tuple[str, str] | None:
    """
    .env 지정 본문 영역.
    HIWORKS_MAIL_BODY_IFRAME + HIWORKS_MAIL_BODY_SELECTOR(기본 body)
    또는 HIWORKS_MAIL_BODY_SELECTOR=iframe.xxx >> body
    """
    iframe_sel = (os.getenv("HIWORKS_MAIL_BODY_IFRAME") or "").strip()
    inner_sel = (os.getenv("HIWORKS_MAIL_BODY_INNER_SELECTOR") or "body").strip() or "body"
    combined = (os.getenv("HIWORKS_MAIL_BODY_SELECTOR") or "").strip()

    if combined and ">>" in combined:
        iframe_sel, inner_sel = (p.strip() for p in combined.split(">>", 1))
    elif combined and not iframe_sel and ">>" not in combined:
        loc = page.locator(combined).first
        try:
            tag = loc.evaluate("el => el.tagName", timeout=5000)
            if (tag or "").upper() == "IFRAME":
                iframe_sel = combined
            else:
                loc.wait_for(state="visible", timeout=12_000)
                html = sanitize_digest_html(loc.evaluate("el => el.innerHTML || ''") or "")
                text = _normalize_body_text(loc.inner_text(timeout=8000))
                if "Boannews" in text or "Boannews" in html or "원문 보기" in text:
                    return text, html
                return None
        except (PlaywrightTimeout, Exception):
            pass
    elif combined.lower().startswith("iframe") and ">>" not in combined and not iframe_sel:
        iframe_sel = combined

    if not iframe_sel:
        iframe_sel = DEFAULT_MAIL_BODY_IFRAME

    # #viewContentIframeId 는 메일 본문 전용 iframe 이므로(목록/사이드 메뉴가 섞이지 않음)
    # digest 형식이 아니어도(예: 일반 테스트 메일) 찾은 내용을 그대로 신뢰한다.
    # digest 여부 판정은 호출부(run_web_mail_board_pipeline)에서 별도로 처리한다.
    extracted = _extract_view_content_iframe(page, iframe_sel)
    if extracted:
        return extracted
    return None


def _wait_for_digest_content(page, timeout_ms: int = 25_000) -> None:
    last_err = None
    for marker in _DIGEST_MARKERS:
        try:
            page.get_by_text(marker, exact=False).first.wait_for(
                state="visible", timeout=timeout_ms // max(len(_DIGEST_MARKERS), 1)
            )
            return
        except PlaywrightTimeout as exc:
            last_err = exc
    if last_err:
        raise last_err


def _extract_from_tall_iframes(page) -> tuple[str, str]:
    """HTML digest → (plain text, innerHTML). 높이 큰 iframe 우선."""
    best_text = ""
    best_html = ""
    best_h = 0
    for iframe in page.locator("iframe").all():
        try:
            box = iframe.bounding_box()
            if not box or box.get("height", 0) < 80:
                continue
            frame = iframe_frame(iframe, timeout_ms=5000)
            if not frame:
                continue
            html = frame.evaluate(
                """() => {
                document.querySelectorAll('script').forEach(s => s.remove());
                const h2 = [...document.querySelectorAll('h2')].find(
                  el => (el.textContent || '').includes('Boannews')
                );
                const root = h2 && (
                  h2.closest('div[style*="max-width"]') ||
                  h2.closest('div')
                );
                if (root) return root.outerHTML;
                return document.body ? document.body.innerHTML : '';
              }"""
            ) or ""
            html = sanitize_digest_html(html)
            text = (frame.locator("body").inner_text(timeout=4000) or "").strip()
            if not text and not html:
                continue
            if not any(m in text or m in html for m in _DIGEST_MARKERS):
                if _mail_chrome_score(text) > 0:
                    continue
            h = box.get("height", 0)
            if h >= best_h and len(text) >= len(best_text):
                best_h = h
                best_text = text
                best_html = html
        except Exception:
            continue
    return best_text, sanitize_digest_html(best_html)


def _extract_body_from_iframes(page) -> str:
    text, _ = _extract_from_tall_iframes(page)
    return text


def _extract_body_digest_region(page) -> tuple[str, str]:
    """digest 본문 블록 (Boannews·원문 보기 포함, 편지함 UI 제외)."""
    try:
        result = page.evaluate(
            """() => {
            const markers = ['Boannews', '보안뉴스 요약', '원문 보기'];
            const hasMarker = (t) => markers.some(m => (t || '').includes(m));
            const chrome = /받은\\s*메일함|받은편지함|전체\\s*메일함|상단\\s*메뉴|스팸\\s*메일함|다른\\s*작업|메일\\s*환경설정|바로가기/;
            let best = null;
            for (const el of document.querySelectorAll('div, section, article, main')) {
              const t = (el.innerText || '').trim();
              if (t.length < 100 || t.length > 80000) continue;
              if (!hasMarker(t)) continue;
              if (chrome.test(t.slice(0, 700))) continue;
              const links = el.querySelectorAll('a[href^="http"]').length;
              if (links < 2) continue;
              const score = links * 2000 - t.length;
              if (!best || score > best.score)
                best = { text: t, html: el.innerHTML || '', score };
            }
            return best || { text: '', html: '' };
          }"""
        )
        return ((result or {}).get("text") or "").strip(), ((result or {}).get("html") or "").strip()
    except Exception:
        return "", ""


def _extract_body(page) -> tuple[str, str]:
    """(plain text, html fragment for board editor)."""
    wait_for_mail_read_ui(page, timeout_ms=20_000)
    try:
        _wait_for_digest_in_mail_iframe(page, timeout_ms=30_000)
    except PlaywrightTimeout:
        try:
            _wait_for_digest_content(page, timeout_ms=15_000)
        except PlaywrightTimeout:
            pass
    page.wait_for_timeout(1500)

    configured = _extract_via_configured_mail_body(page)
    if configured:
        return configured

    iframe_text, iframe_html = _extract_from_tall_iframes(page)
    if iframe_text and any(m in iframe_text for m in _DIGEST_MARKERS):
        return _normalize_body_text(iframe_text), iframe_html

    digest_text, digest_html = _extract_body_digest_region(page)
    if digest_text and _mail_chrome_score(digest_text) <= 1:
        return _normalize_body_text(digest_text), sanitize_digest_html(digest_html)

    if iframe_text and _mail_chrome_score(iframe_text) <= 1:
        return _normalize_body_text(_anchor_digest_text(iframe_text)), sanitize_digest_html(
            iframe_html
        )

    for sel in (
        "iframe#contentFrame",
        "iframe.mail_content",
        "[class*='mailView'] [class*='content']",
        "[class*='MailView'] [class*='content']",
        "[class*='mailView']",
        "[class*='MailView']",
        "#mailReadArea",
        "[class*='MessageBody']",
        "[class*='message-body']",
        "article",
    ):
        loc = page.locator(sel).first
        try:
            if loc.count() == 0:
                continue
            if "iframe" in sel:
                frame = iframe_frame(loc, timeout_ms=5000)
                if frame:
                    text = (frame.locator("body").inner_text(timeout=5000) or "").strip()
                    html = sanitize_digest_html(
                        frame.locator("body").evaluate("b => b.innerHTML || ''") or ""
                    )
                    if text and _mail_chrome_score(text) <= 2:
                        return _normalize_body_text(_anchor_digest_text(text)), html
            else:
                loc.wait_for(state="visible", timeout=3000)
                text = (loc.inner_text(timeout=5000) or "").strip()
                html = sanitize_digest_html(loc.evaluate("el => el.innerHTML || ''") or "")
                if text and _mail_chrome_score(text) <= 2:
                    return _normalize_body_text(_anchor_digest_text(text)), html
        except (PlaywrightTimeout, Exception):
            continue

    if digest_text:
        return _trim_leading_mail_chrome(digest_text), sanitize_digest_html(digest_html)

    if iframe_text:
        return _trim_leading_mail_chrome(iframe_text), sanitize_digest_html(iframe_html)

    # 마지막 수단: digest 형식이 아니어도 본문 iframe 원문을 그대로 반환.
    # 호출부가 digest 여부를 판정해 게시 여부를 결정하므로, 여기서 예외를 던져
    # 전체 배치(나머지 메일들)를 중단시키지 않는다.
    print(
        f"  경고: 메일 본문 iframe({DEFAULT_MAIL_BODY_IFRAME}) 내용을 읽지 못했습니다. "
        "본문 없이 건너뜁니다.",
        flush=True,
    )
    return "", ""


def _subject_from_list_text(text: str, subject_tag: str) -> str:
    for line in (text or "").split("\n"):
        line = line.strip()
        if subject_tag in line:
            return line
    return ""


def _is_plausible_digest_subject(subject: str, subject_tag: str) -> bool:
    if not subject or subject_tag not in subject:
        return False
    if re.fullmatch(r"[\w.+-]+@[\w.-]+\.\w+", subject.strip()):
        return False
    return True


def _collect_list_links(page, subject_tag: str) -> list[tuple[str, str, str]]:
    """returns (uid, subject, mail_url)"""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    base = page.url

    row_loc = page.locator(
        f"[role='row']:has-text('{subject_tag}'), tr:has-text('{subject_tag}'), li:has-text('{subject_tag}')"
    )
    try:
        row_count = row_loc.count()
    except Exception:
        row_count = 0

    for i in range(row_count):
        row = row_loc.nth(i)
        try:
            row_text = (row.inner_text() or "").strip()
            subj = _subject_from_list_text(row_text, subject_tag)
            if not _is_plausible_digest_subject(subj, subject_tag):
                continue
            link = row.locator("a[href*='/view/'], a[href*='/read/'], a[href*='/mail/']").first
            href = _normalize_mail_url(link.get_attribute("href") or "", base)
            if not href:
                continue
            if href in seen:
                continue
            seen.add(href)
            found.append((href, subj, href))
        except Exception:
            continue

    if found:
        return found

    for el in page.locator("a[href*='/view/'], a[href*='/read/'], a[href*='/mail/']").all():
        try:
            text = (el.inner_text() or "").strip()
            subj = _subject_from_list_text(text, subject_tag)
            if not _is_plausible_digest_subject(subj, subject_tag):
                continue
            href = _normalize_mail_url(el.get_attribute("href") or "", base)
            if not href or href in seen:
                continue
            seen.add(href)
            found.append((href, subj, href))
        except Exception:
            continue

    return found


def fetch_security_news_mails_web(
    subject_tag: str = "[보안뉴스]",
) -> list[InboundMail]:
    list_url = (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip()
    if not list_url:
        raise RuntimeError(
            "HIWORKS_MAIL_LIST_URL 이 .env 에 없습니다. "
            "예: https://mails.office.hiworks.com/list/personal/717?page=1"
        )

    headless = os.getenv("HIWORKS_PLAYWRIGHT_HEADLESS", "0").strip() in ("1", "true", "yes")
    max_pages = int((os.getenv("HIWORKS_MAIL_LIST_MAX_PAGES") or "3").strip() or "3")
    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)

    results: list[InboundMail] = []
    seen_uid: set[str] = set()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            locale="ko-KR",
        )
        attach_dialog_auto_dismiss(context)
        page = context.pages[0] if context.pages else context.new_page()
        page = ensure_mail_session_or_exit(page, list_url)

        for page_num in range(1, max_pages + 1):
            url = re.sub(r"page=\d+", f"page={page_num}", list_url)
            if "page=" not in url:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}page={page_num}"

            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)
            if needs_login(page):
                ok, page = wait_until_mail_session(page, list_url)
                if not ok:
                    context.close()
                    sys.exit(2)

            links = _collect_list_links(page, subject_tag)
            if not links and page_num == 1:
                break
            if not links:
                break

            for uid, subject, mail_url in links:
                if uid in seen_uid:
                    continue
                seen_uid.add(uid)

                text_body = ""
                html_body = ""
                if mail_url:
                    view = context.new_page()
                    try:
                        view.goto(mail_url, wait_until="domcontentloaded", timeout=60_000)
                        view.wait_for_timeout(1500)
                        if not needs_login(view):
                            text_body, html_body = _extract_body(view)
                    finally:
                        view.close()
                else:
                    text_body = subject

                results.append(
                    InboundMail(
                        pop_uid=uid,
                        subject=subject,
                        text_body=text_body,
                        html_body=html_body,
                    )
                )

            if len(links) < 5:
                break

        context.close()

    return results


def _open_mail_read_page(page, mail: InboundMail, list_url: str, subject_tag: str) -> None:
    mail_url = (mail.pop_uid or "").strip()
    if mail_url.startswith("http"):
        page.goto(mail_url, wait_until="domcontentloaded", timeout=60_000)
    else:
        page.goto(list_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        link = page.locator("a").filter(has_text=subject_tag).filter(has_text=mail.subject[:50]).first
        link.click(timeout=15_000)
    page.wait_for_timeout(2000)
    try:
        _wait_for_digest_in_mail_iframe(page, timeout_ms=25_000)
    except PlaywrightTimeout:
        pass
    if needs_login(page):
        ok, page = wait_until_mail_session(page, list_url)
        if not ok:
            sys.exit(2)
    if not wait_for_mail_ui(page):
        raise RuntimeError(f"메일 읽기 화면을 열지 못했습니다: {page.url}")


def _read_mail_for_post(page, mail: InboundMail, subject_tag: str) -> tuple[str, str, str]:
    subj = mail.subject or ""
    if not _is_plausible_digest_subject(subj, subject_tag):
        subj = ""
    text_body, html_body = _extract_body(page)
    if not subj:
        for sel in ("h1", "h2", "[class*='subject']", "[class*='Subject']"):
            try:
                t = page.locator(sel).first.inner_text(timeout=2000).strip()
                if subject_tag in t:
                    subj = t
                    break
            except Exception:
                continue
    if not subj:
        subj = subject_tag
    body = text_body or subj
    return subj, body, html_body or ""


def run_web_mail_board_pipeline(
    subject_tag: str,
    posted_uids: set[str],
    dry_run: bool = False,
    on_each_success: Callable[[InboundMail], None] | None = None,
) -> list[InboundMail]:
    """
    브라우저 1회: 편지함 → 메일 본문 읽기 → 게시판 글쓰기 URL에 등록.
    """
    from hiworks_board import ensure_board_write_page, fill_board_write_form

    list_url = (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip()
    write_url = (os.getenv("HIWORKS_BOARD_WRITE_URL") or "").strip()
    if not list_url:
        raise RuntimeError("HIWORKS_MAIL_LIST_URL 이 필요합니다.")
    if not write_url:
        raise RuntimeError("HIWORKS_BOARD_WRITE_URL 이 필요합니다.")

    headless = os.getenv("HIWORKS_PLAYWRIGHT_HEADLESS", "0").strip() in ("1", "true", "yes")
    max_pages = int((os.getenv("HIWORKS_MAIL_LIST_MAX_PAGES") or "3").strip() or "3")
    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)

    collected: list[InboundMail] = []
    seen_uid: set[str] = set()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            locale="ko-KR",
        )
        attach_dialog_auto_dismiss(context)
        page = context.pages[0] if context.pages else context.new_page()

        page = ensure_mail_session_or_exit(page, list_url)

        for page_num in range(1, max_pages + 1):
            url = re.sub(r"page=\d+", f"page={page_num}", list_url)
            if "page=" not in url:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}page={page_num}"

            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
            if needs_login(page):
                ok, page = wait_until_mail_session(page, list_url)
                if not ok:
                    context.close()
                    sys.exit(2)

            links = _collect_list_links(page, subject_tag)
            if not links:
                break

            for uid, subject, mail_url in links:
                if uid in seen_uid:
                    continue
                seen_uid.add(uid)
                href = mail_url or uid
                collected.append(
                    InboundMail(
                        pop_uid=href,
                        subject=subject,
                        text_body="",
                        html_body="",
                    )
                )

            if len(links) < 5:
                break

        pending = [m for m in collected if m.pop_uid not in posted_uids]
        if dry_run or not pending:
            context.close()
            return pending

        try:
            for i, mail in enumerate(pending, start=1):
                print(
                    f"[{i}/{len(pending)}] 게시 중: {mail.subject[:60]}…",
                    flush=True,
                )
                try:
                    _open_mail_read_page(page, mail, list_url, subject_tag)
                    title, body, body_html = _read_mail_for_post(page, mail, subject_tag)
                    if not _looks_like_boannews_digest(body, body_html):
                        print(
                            f"  digest 형식 아님 — 건너뜀 (Boannews/원문 보기 없음): {mail.subject[:55]}",
                            flush=True,
                        )
                        if on_each_success:
                            on_each_success(mail)
                        continue
                    page = ensure_board_write_page(page, write_url)
                    fill_board_write_form(page, title, body, body_html=body_html)
                    if on_each_success:
                        on_each_success(mail)
                except Exception as exc:
                    # 메일 1건 처리 실패가 나머지 대기 메일 전체를 막지 않도록 건너뛴다.
                    # posted_uids 에는 추가하지 않아 다음 실행에서 재시도된다.
                    print(
                        f"  오류 — 건너뜀 ({exc}): {mail.subject[:55]}",
                        flush=True,
                    )
                    continue
        finally:
            pause = (os.getenv("HIWORKS_BROWSER_CLOSE_DELAY_SEC") or "2").strip()
            try:
                sec = max(0, min(30, int(pause)))
            except ValueError:
                sec = 2
            if sec:
                page.wait_for_timeout(sec * 1000)
            context.close()

    return pending
