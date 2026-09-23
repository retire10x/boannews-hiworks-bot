"""하이웍스 Playwright 세션 판별 (웹메일·게시)."""
import os
import sys
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from hiworks_board import try_prefill_login_id

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

HEADLESS_LOGIN_MAX_SEC = 90


def playwright_headless_mode() -> bool:
    return os.getenv("HIWORKS_PLAYWRIGHT_HEADLESS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _mail_list_dom_ready(page, *, quick: bool = True) -> bool:
    """URL과 무관하게 웹메일 목록·편지 UI가 보이면 True."""
    timeout = 800 if quick else 2500
    probes = (
        "text=[보안뉴스]",
        "a[href*='/view/']",
        "a[href*='/read/']",
        "a[href*='/mail/']",
        "[role='row']",
        "[role='grid']",
        "table tbody tr",
    )
    for sel in probes:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=timeout):
                return True
        except (PlaywrightTimeout, Exception):
            continue
    return False


def _url_looks_like_mail_list(url: str) -> bool:
    u = (url or "").lower()
    if "login.office.hiworks.com" in u:
        return False
    if "mails.office.hiworks.com" not in u:
        return False
    return "/list/" in u or "list/personal" in u or "list/inbox" in u or "/view/" in u


def needs_login(page) -> bool:
    """로그인 URL이어도 편지함 UI가 보이면 False."""
    if mail_list_ready(page, quick_dom=True):
        return False
    return "login.office.hiworks.com" in (page.url or "").lower()


def mail_list_ready(page, *, quick_dom: bool = False) -> bool:
    """웹메일 편지함 목록 화면 (읽기 화면과 다름 — '다른 작업' 없음)."""
    if _mail_list_dom_ready(page, quick=quick_dom):
        return True

    try:
        for frame in page.frames:
            if _url_looks_like_mail_list(frame.url or ""):
                return True
            try:
                if frame.locator("text=[보안뉴스]").first.is_visible(timeout=500):
                    return True
            except Exception:
                pass
    except Exception:
        pass

    url = (page.url or "").lower()
    if "login.office.hiworks.com" in url:
        return False
    if "mails.office.hiworks.com" not in url:
        return False
    if "/list/" in url or "list/personal" in url or "list/inbox" in url:
        return True
    if not quick_dom:
        for sel in ("text=[보안뉴스]", "table", "[role='row']", "[role='grid']"):
            try:
                page.locator(sel).first.wait_for(state="visible", timeout=3000)
                return True
            except PlaywrightTimeout:
                continue
    return True


def pick_mail_page(context: "BrowserContext", preferred: "Page | None" = None) -> "Page | None":
    """컨텍스트의 모든 탭 중 편지함이 열린 탭을 선택."""
    chosen = None
    for p in context.pages:
        if mail_list_ready(p, quick_dom=True):
            chosen = p
            break
    if chosen is None:
        for p in context.pages:
            u = (p.url or "").lower()
            if "mails.office.hiworks.com" in u and "login.office.hiworks.com" not in u:
                chosen = p
                break
    if chosen is None:
        return preferred
    if preferred is not None and chosen is not preferred:
        print(
            f"  편지함 탭으로 전환: {(chosen.url or '')[:90]}",
            flush=True,
        )
    try:
        chosen.bring_to_front()
    except Exception:
        pass
    return chosen


def _dump_context_urls(context: "BrowserContext") -> None:
    urls = [((p.url or "")[:85]) for p in context.pages]
    print(f"  현재 탭 {len(urls)}개: {urls}", flush=True)


def wait_for_mail_read_ui(page, timeout_ms: int = 25_000) -> bool:
    """메일 읽기 화면 ('다른 작업' 등)."""
    probes = (
        "span:has-text('다른 작업')",
        "span.DropdownButton_label__zKQKu",
        "[data-testid='btn-post-submit']",
    )
    per = max(3000, timeout_ms // max(len(probes), 1))
    for sel in probes:
        try:
            page.locator(sel).first.wait_for(state="visible", timeout=per)
            return True
        except PlaywrightTimeout:
            continue
    return False


def wait_for_mail_ui(page, timeout_ms: int = 25_000) -> bool:
    """목록 또는 읽기 화면."""
    if mail_list_ready(page):
        return True
    return wait_for_mail_read_ui(page, timeout_ms)


def wait_until_url_ready(
    page: "Page",
    target_url: str,
    is_ready: Callable[..., bool],
    *,
    timeout_sec: int = 600,
    intro: str,
    ready_message: str,
    pick_page: Callable[["BrowserContext", "Page | None"], "Page | None"] | None = None,
    url_wait_glob: str | None = None,
    wait_timeout_message: str = "대기 시간 초과 (10분).",
) -> tuple[bool, "Page"]:
    """로그인·OTP 후 target_url 화면(is_ready)까지 대기."""
    manual = (os.getenv("HIWORKS_SETUP_MANUAL_ENTER") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    pick = pick_page or (lambda ctx, pref: pref)

    print(intro, flush=True)
    if playwright_headless_mode():
        print(
            "  ※ Headless 모드: Chromium 창이 보이지 않습니다. OTP는 불가능합니다.\n"
            "    run_board_poster.ps1 또는 HIWORKS_PLAYWRIGHT_HEADLESS=0 로 실행하세요.",
            flush=True,
        )
    context = page.context
    page = pick(context, page) or page
    if needs_login(page):
        try_prefill_login_id(page)

    deadline = time.time() + timeout_sec
    wait_started = time.time()
    headless_cap = int(
        (os.getenv("HIWORKS_HEADLESS_LOGIN_MAX_SEC") or str(HEADLESS_LOGIN_MAX_SEC)).strip()
        or HEADLESS_LOGIN_MAX_SEC
    )
    headless_login_deadline = (
        wait_started + headless_cap if playwright_headless_mode() else None
    )
    last_msg = 0.0
    last_goto = 0.0
    last_tab_dump = 0.0

    while time.time() < deadline:
        page = pick(context, page) or page
        if is_ready(page, quick_dom=False):
            print(ready_message, flush=True)
            if manual:
                input("계속하려면 Enter… ")
            return True, page

        if needs_login(page):
            now = time.time()

            if headless_login_deadline is not None and now >= headless_login_deadline:
                print(
                    "Headless 로그인 대기 시간 초과 — 브라우저 창 없이 OTP를 완료할 수 없습니다.\n"
                    "  PowerShell: .\\scripts\\run_board_poster.ps1\n"
                    "  (Chromium 창이 뜨면 그 창에서 OTP 입력)",
                    flush=True,
                )
                return False, page

            if url_wait_glob:
                try:
                    page.wait_for_url(url_wait_glob, timeout=1500)
                    page = pick(context, page) or page
                    if is_ready(page, quick_dom=False):
                        print(ready_message, flush=True)
                        if manual:
                            input("계속하려면 Enter… ")
                        return True, page
                except PlaywrightTimeout:
                    pass

            if now - last_msg >= 15:
                print("  로그인·OTP 입력 대기 중… (화면을 새로고침하지 않습니다)", flush=True)
                last_msg = now
            if now - last_tab_dump >= 30:
                _dump_context_urls(context)
                last_tab_dump = now
            time.sleep(1)
            continue

        now = time.time()
        if now - last_goto >= 8:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(800)
            except Exception:
                pass
            last_goto = now
            page = pick(context, page) or page
            if is_ready(page, quick_dom=False):
                print(ready_message, flush=True)
                if manual:
                    input("계속하려면 Enter… ")
                return True, page

        time.sleep(1)

    _dump_context_urls(context)
    print(wait_timeout_message, flush=True)
    return False, page


def wait_until_mail_session(
    page: "Page", list_url: str, timeout_sec: int = 600
) -> tuple[bool, "Page"]:
    return wait_until_url_ready(
        page,
        list_url,
        mail_list_ready,
        timeout_sec=timeout_sec,
        intro=(
            "브라우저에서 ID → 다음 → 비밀번호/OTP 를 입력하세요.\n"
            "  로그인 완료 후 편지함 화면이 뜨면 자동으로 이어서 진행합니다."
        ),
        ready_message="웹메일 편지함 준비됨.",
        pick_page=pick_mail_page,
        url_wait_glob="**mails.office.hiworks.com/**",
        wait_timeout_message="로그인·편지함 대기 시간 초과 (10분).",
    )


def ensure_mail_session_or_exit(page: "Page", list_url: str) -> "Page":
    """세션 없으면: 스케줄러는 종료, PC 수동 실행은 브라우저에서 로그인 대기."""
    context = page.context
    page = pick_mail_page(context, page) or page
    if not needs_login(page) and mail_list_ready(page, quick_dom=False):
        return page

    page.goto(list_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    page = pick_mail_page(context, page) or page
    if not needs_login(page) and mail_list_ready(page, quick_dom=False):
        return page

    if os.getenv("HIWORKS_SCHEDULED") == "1":
        print(
            "하이웍스 로그인 세션이 없습니다 (스케줄러 모드).\n"
            "  PC 앞에서 run_board_poster.ps1 을 수동 실행해 로그인하세요.",
            flush=True,
        )
        sys.exit(2)
    ok, page = wait_until_mail_session(page, list_url)
    if not ok:
        sys.exit(2)
    return page
