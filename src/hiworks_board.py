import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from playwright_iframe import iframe_frame


def _profile_dir() -> Path:
    raw = os.getenv("HIWORKS_PLAYWRIGHT_USER_DATA_DIR", ".hiworks_browser_profile")
    path = Path(raw)
    if not path.is_absolute():
        from env_loader import PROJECT_ROOT

        path = PROJECT_ROOT / path
    return path


def _login_id_from_env() -> str:
    return (
        (os.getenv("HIWORKS_LOGIN_ID") or "").strip()
        or (os.getenv("HIWORKS_SMTP_USER") or "").strip()
        or (os.getenv("HIWORKS_POP3_USER") or "").strip()
    )


def try_prefill_login_id(page) -> None:
    """
    로그인 1단계(ID)에서만 이메일 자동 입력.
    비밀번호 화면(2단계)이면 건드리지 않음. '다음'은 사용자가 직접 누름.
    """
    flag = (os.getenv("HIWORKS_LOGIN_ID_PREFILL") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return
    if "login.office.hiworks.com" not in (page.url or "").lower():
        return

    login_id = _login_id_from_env()
    if not login_id:
        return

    try:
        if page.locator("input[type='password']").first.is_visible(timeout=1000):
            return
    except PlaywrightTimeout:
        pass

    default_selectors = (
        "input[type='email'], "
        "input[name='userId'], "
        "input[name='email'], "
        "input[placeholder*='onhiworks'], "
        "input[placeholder*='@']"
    )
    selectors = (os.getenv("HIWORKS_LOGIN_ID_SELECTOR") or "").strip() or default_selectors
    for sel in (s.strip() for s in selectors.split(",") if s.strip()):
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=3000)
            current = (loc.input_value() or "").strip()
            if current == login_id:
                return
            if current:
                return
            loc.fill(login_id, timeout=3000)
            return
        except (PlaywrightTimeout, Exception):
            continue


def attach_dialog_auto_dismiss(context) -> None:
    """alert/confirm 자동 닫기. 이미 닫힌 다이얼로그는 무시(Playwright 레이스 방지)."""

    def _handle(dialog) -> None:
        try:
            dialog.dismiss()
        except Exception:
            try:
                dialog.accept()
            except Exception:
                pass

    context.on("dialog", _handle)


def _title_locator_candidates(page):
    custom = (os.getenv("HIWORKS_BOARD_SELECTOR_TITLE") or "").strip()
    if custom:
        yield page.locator(custom).first
        return
    yield page.get_by_placeholder(re.compile(r"제목", re.I))
    for sel in (
        "input[placeholder*='제목']",
        "textarea[placeholder*='제목']",
        "[data-testid*='title' i] input",
        "[data-testid*='title' i]",
        "input[name='title']",
        "input[name='subject']",
        "#title",
        "#subject",
        ".mantine-TextInput-input:not([placeholder*='@'])",
    ):
        yield page.locator(sel).first


def _body_locator_candidates(page):
    custom = (os.getenv("HIWORKS_BOARD_SELECTOR_BODY") or "").strip()
    if custom:
        yield page.locator(custom).first
        return
    yield page.get_by_placeholder(re.compile(r"내용|본문", re.I))
    for sel in (
        ".se-main-container .se-text-paragraph",
        ".se-main-container [contenteditable='true']:not(.se-clipboard)",
        ".se-wrapper [contenteditable='true']:not(.se-clipboard)",
        "textarea[name='content']",
        "textarea#content",
        "[class*='editor'] [contenteditable='true']:not(.se-clipboard)",
        ".ProseMirror",
        "iframe[id*='editor' i]",
        "iframe",
        "[contenteditable='true']:not(.se-clipboard)",
    ):
        yield page.locator(sel).first


def _body_element_usable(loc) -> bool:
    try:
        cls = (loc.get_attribute("class") or "").lower()
        if "se-clipboard" in cls:
            return False
        if not loc.is_visible():
            return False
        box = loc.bounding_box()
        if not box:
            return False
        return box.get("height", 0) > 12 and box.get("width", 0) > 40
    except Exception:
        return False


def _wait_smart_editor_ready(page, timeout_ms: int = 30_000) -> None:
    """네이버 SmartEditor — 본문은 iframe.se-contents-edit 안에 로드됨."""
    iframe = page.locator("iframe.se-contents-edit").first
    iframe.wait_for(state="attached", timeout=timeout_ms)
    page.wait_for_function(
        """() => {
            const iframe = document.querySelector('iframe.se-contents-edit');
            if (!iframe) return false;
            const r = iframe.getBoundingClientRect();
            if (r.height < 40 || r.width < 100) return false;
            const loader = document.querySelector('.se-loader');
            if (loader) {
                const lr = loader.getBoundingClientRect();
                if (lr.width > 0 && lr.height > 0) return false;
            }
            return true;
        }""",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(400)


def _type_multiline(page, text: str) -> None:
    """
    개행이 포함된 본문을 contenteditable 에 입력.
    insert_text 한 번에 '\n'을 통째로 넣으면 SmartEditor(contenteditable) 가
    이를 줄바꿈으로 인식하지 못하고 한 줄로 이어붙여, 실제 Enter 키를 눌러
    줄 단위로 끊어 넣는다.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line:
            page.keyboard.insert_text(line)
        if i < len(lines) - 1:
            page.keyboard.press("Enter")


def _write_clipboard_html(page, html: str, text: str) -> bool:
    """OS 클립보드에 HTML+텍스트를 같이 올려 실제 붙여넣기(Ctrl+V)로 서식을 반영."""
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:
        pass
    try:
        page.evaluate(
            """async ({html, text}) => {
                const item = new ClipboardItem({
                    'text/html': new Blob([html], { type: 'text/html' }),
                    'text/plain': new Blob([text], { type: 'text/plain' }),
                });
                await navigator.clipboard.write([item]);
            }""",
            {"html": html, "text": text},
        )
        return True
    except Exception:
        return False


def _paste_rich_content(page, loc, html: str, text: str) -> bool:
    """
    실제 Ctrl+V 붙여넣기로 서식(굵게·링크 등) 반영.
    innerHTML 직접 대입과 달리 브라우저의 실제 paste 이벤트라
    SmartEditor 가 자기 방식대로 정상 처리한다.
    """
    if not _write_clipboard_html(page, html, text):
        return False
    try:
        loc.click(force=True, timeout=6000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.press("Control+V")
        return True
    except Exception:
        return False


def _fill_smart_editor_iframe(page, text: str, html: str = "") -> bool:
    """
    실제 키 입력(keyboard)/붙여넣기(paste)로 SmartEditor 본문에 입력.
    innerHTML/innerText 직접 대입 + 합성 input 이벤트는 화면엔 보이지만
    SmartEditor 내부 상태(등록 시 실제로 서버에 전송되는 값)에는 반영되지 않아
    "제목만 있고 본문 없는 글"이 등록되는 문제가 있었다.
    """
    iframe_css = (os.getenv("HIWORKS_BOARD_EDITOR_IFRAME") or "iframe.se-contents-edit").strip()
    try:
        _wait_smart_editor_ready(page)
    except PlaywrightTimeout:
        return False

    editor = page.frame_locator(iframe_css)
    targets = (
        ".se-contents",
        ".se-text-paragraph",
        "[contenteditable='true']",
        ".se-module-text",
        "p",
        "body",
    )
    for sel in targets:
        loc = editor.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=6000)
            if html and _paste_rich_content(page, loc, html, text):
                return True
            loc.click(force=True, timeout=6000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            _type_multiline(page, text)
            return True
        except Exception:
            continue

    try:
        page.locator(iframe_css).first.click(timeout=5000)
        _type_multiline(page, text)
        return True
    except Exception:
        return False


def _fill_board_body(page, text: str, *, html: str = "") -> None:
    """SmartEditor( iframe )·textarea 등 본문 입력."""
    text = text if len(text) <= 12_000 else text[:12_000] + "\n...(생략)"

    if page.locator("iframe.se-contents-edit, .se-container").count() > 0:
        if _fill_smart_editor_iframe(page, text, html):
            return

    se = page.locator(".se-main-container, .se-wrapper").first
    if se.count() > 0:
        try:
            se.scroll_into_view_if_needed(timeout=8000)
            se.click(timeout=8000)
            target = page.locator(
                ".se-main-container .se-text-paragraph, "
                ".se-main-container [contenteditable='true']:not(.se-clipboard), "
                ".se-wrapper [contenteditable='true']:not(.se-clipboard)"
            ).first
            target.click(force=True, timeout=8000)
            _type_multiline(page, text)
            return
        except Exception:
            pass

    deadline = time.time() + 20
    while time.time() < deadline:
        for loc in _body_locator_candidates(page):
            try:
                if loc.count() == 0 or not _body_element_usable(loc):
                    continue
                tag = (loc.evaluate("el => el.tagName") or "").upper()
                loc.scroll_into_view_if_needed(timeout=3000)
                if tag == "IFRAME":
                    frame = iframe_frame(loc, timeout_ms=5000)
                    if frame:
                        frame.locator("body").click(force=True)
                        frame.locator("body").fill(text)
                        return
                loc.click(force=True, timeout=5000)
                try:
                    loc.fill(text)
                except Exception:
                    _type_multiline(page, text)
                return
            except Exception:
                continue
        page.wait_for_timeout(400)

    raise PlaywrightTimeout(
        "게시판 본문 입력 영역을 찾지 못했습니다 (SmartEditor). "
        "HIWORKS_BOARD_SELECTOR_BODY 를 지정해 보세요."
    )


def _board_body_text(page) -> str:
    """등록 전 검증용: SmartEditor 에 실제로 반영된 텍스트."""
    iframe_css = (os.getenv("HIWORKS_BOARD_EDITOR_IFRAME") or "iframe.se-contents-edit").strip()
    try:
        return (page.frame_locator(iframe_css).locator("body").inner_text(timeout=3000) or "").strip()
    except Exception:
        pass
    try:
        return (page.locator(".se-main-container, .se-wrapper").first.inner_text(timeout=3000) or "").strip()
    except Exception:
        return ""


def _submit_locator_candidates(page):
    custom = (os.getenv("HIWORKS_BOARD_SELECTOR_SUBMIT") or "").strip()
    if custom:
        yield page.locator(custom).first
        return
    yield page.locator('button[data-testid="btn-post-submit"]').first
    yield page.get_by_role("button", name=re.compile(r"^등록$|^저장$|^올리기$"))
    for sel in (
        "button:has-text('등록')",
        "button:has-text('저장')",
        "button:has-text('올리기')",
        "input[type='submit']",
    ):
        yield page.locator(sel).first


def _first_visible(page, candidates, timeout_ms: int = 20_000):
    deadline = time.time() + timeout_ms / 1000
    last_err = None
    while time.time() < deadline:
        for loc in candidates:
            try:
                loc.wait_for(state="visible", timeout=800)
                return loc
            except (PlaywrightTimeout, Exception) as exc:
                last_err = exc
        page.wait_for_timeout(400)
    raise PlaywrightTimeout(f"입력 필드를 찾지 못했습니다: {last_err}")


def board_write_ready(page, *, quick_dom: bool = False) -> bool:
    url = (page.url or "").lower()
    if "login.office.hiworks.com" in url:
        return False
    if "boards.office.hiworks.com" not in url or "postwrite" not in url:
        return False
    timeout = 600 if quick_dom else 1500
    for loc in _title_locator_candidates(page):
        try:
            if loc.count() > 0 and loc.is_visible(timeout=timeout):
                return True
        except Exception:
            continue
    return False


def pick_board_page(context, preferred=None):
    chosen = None
    for p in context.pages:
        if board_write_ready(p, quick_dom=True):
            chosen = p
            break
    if chosen is None:
        for p in context.pages:
            u = (p.url or "").lower()
            if "boards.office.hiworks.com" in u and "postwrite" in u:
                chosen = p
                break
    if chosen is None:
        return preferred
    if preferred is not None and chosen is not preferred:
        print(f"  게시판 글쓰기 탭으로 전환: {(chosen.url or '')[:90]}", flush=True)
    try:
        chosen.bring_to_front()
    except Exception:
        pass
    return chosen


def ensure_board_write_page(page, write_url: str):
    """게시판 글쓰기 URL 로드 + 필요 시 OTP 대기."""
    from hiworks_session import wait_until_url_ready

    page.goto(write_url, wait_until="domcontentloaded", timeout=60_000)
    try:
        page.wait_for_load_state("networkidle", timeout=12_000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(1500)
    page = pick_board_page(page.context, page) or page
    if board_write_ready(page, quick_dom=False):
        return page

    ok, page = wait_until_url_ready(
        page,
        write_url,
        board_write_ready,
        intro=(
            "게시판 글쓰기에 로그인이 필요합니다.\n"
            "  브라우저에서 ID → 비밀번호/OTP 를 입력하세요 (편지함과 동일 계정).\n"
            "  로그인 완료 후 글쓰기 화면이 뜨면 자동으로 이어서 진행합니다."
        ),
        ready_message="게시판 글쓰기 화면 준비됨.",
        pick_page=pick_board_page,
        url_wait_glob="**boards.office.hiworks.com/**",
        wait_timeout_message="게시판 글쓰기 로그인·대기 시간 초과 (10분).",
    )
    if not ok:
        sys.exit(2)
    return page


def fill_board_write_form(page, title: str, body: str, *, body_html: str = "") -> None:
    """게시판 글쓰기 화면에서 제목·본문 입력 후 등록."""
    if not board_write_ready(page, quick_dom=False):
        write_url = (os.getenv("HIWORKS_BOARD_WRITE_URL") or "").strip()
        if write_url:
            page = ensure_board_write_page(page, write_url)

    print("  제목 입력…", flush=True)
    title_loc = _first_visible(page, list(_title_locator_candidates(page)))
    title_loc.fill(title)
    page.wait_for_timeout(600)

    print("  본문 입력 (에디터 로드 대기)…", flush=True)
    for attempt in range(1, 4):
        # 1차 시도는 서식(굵게·링크) 유지를 위해 붙여넣기, 실패 시 순수 텍스트로 재시도.
        _fill_board_body(page, body, html=(body_html if attempt == 1 else ""))
        page.wait_for_timeout(500)
        if len(_board_body_text(page)) >= 10:
            break
        print(f"  본문이 비어 있음 — 재시도 ({attempt}/3)", flush=True)
    else:
        raise RuntimeError(
            "게시판 본문이 비어 있습니다 (에디터에 내용이 반영되지 않아 등록을 중단합니다)."
        )

    print("  등록 버튼 클릭…", flush=True)
    submit = _first_visible(page, list(_submit_locator_candidates(page)), timeout_ms=15_000)
    submit.scroll_into_view_if_needed(timeout=5000)
    submit.click(force=True, timeout=15_000)
    page.wait_for_timeout(3000)
    print("  게시 요청 완료.", flush=True)


def post_to_board(title: str, body: str) -> None:
    write_url = (os.getenv("HIWORKS_BOARD_WRITE_URL") or "").strip()
    if not write_url:
        raise RuntimeError("HIWORKS_BOARD_WRITE_URL 이 .env 에 없습니다.")

    headless = os.getenv("HIWORKS_PLAYWRIGHT_HEADLESS", "0").strip() in (
        "1",
        "true",
        "yes",
    )
    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            locale="ko-KR",
        )
        attach_dialog_auto_dismiss(context)
        page = context.pages[0] if context.pages else context.new_page()
        page = ensure_board_write_page(page, write_url)
        fill_board_write_form(page, title, body)
        context.close()
