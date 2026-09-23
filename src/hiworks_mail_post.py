"""하이웍스 웹메일: 메일 → 다른 작업 → 게시판에 등록하기 → 게시판 선택 → 확인."""
import os
import re
import sys
from typing import Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from hiworks_board import (
    _profile_dir,
    attach_dialog_auto_dismiss,
)
from hiworks_session import needs_login, wait_for_mail_ui
from mail_inbox import InboundMail


def _board_name_from_env() -> str:
    return (
        (os.getenv("HIWORKS_BOARD_NAME") or "").strip()
        or "정보보안 뉴스레터"
    )


def _click_first(page, locators: list, timeout: int = 8000) -> bool:
    for loc in locators:
        try:
            loc.first.wait_for(state="visible", timeout=timeout)
            loc.first.click(timeout=timeout)
            return True
        except (PlaywrightTimeout, Exception):
            continue
    return False


def _open_mail_to_board_flow(page) -> None:
    """메일 읽기 화면: 다른 작업 → 게시판에 등록하기."""
    menu = (os.getenv("HIWORKS_MAIL_OTHER_ACTIONS_LABEL") or "다른 작업").strip()
    action = (os.getenv("HIWORKS_MAIL_POST_MENU_LABEL") or "게시판에 등록하기").strip()

    menu_locators = [
        page.locator("span.DropdownButton_label__zKQKu"),
        page.get_by_text(menu, exact=True),
        page.locator(f"span:has-text('{menu}')"),
    ]
    custom_menu = (os.getenv("HIWORKS_MAIL_OTHER_ACTIONS_SELECTOR") or "").strip()
    if custom_menu:
        menu_locators.insert(0, page.locator(custom_menu))

    if not _click_first(page, menu_locators):
        raise RuntimeError(
            f"메일 화면에서 '{menu}' 버튼을 찾지 못했습니다. "
            "HIWORKS_MAIL_OTHER_ACTIONS_SELECTOR 를 확인하세요."
        )

    page.wait_for_timeout(500)

    action_locators = [
        page.locator("span.DropdownOption_truncate__XDBkZ", has_text=action),
        page.get_by_text(action, exact=True),
        page.locator(f"span:has-text('{action}')"),
    ]
    custom = (os.getenv("HIWORKS_MAIL_POST_MENU_SELECTOR") or "").strip()
    if custom:
        for sel in (s.strip() for s in custom.split(",") if s.strip()):
            action_locators.insert(0, page.locator(sel))

    if not _click_first(page, action_locators):
        raise RuntimeError(
            f"'{action}' 메뉴를 찾지 못했습니다. "
            "HIWORKS_MAIL_POST_MENU_SELECTOR 를 확인하세요."
        )

    try:
        page.wait_for_url(
            re.compile(r"boards\.office\.hiworks\.com/board/postwrite/mailtoboard/\d+/new"),
            timeout=60_000,
        )
    except PlaywrightTimeout:
        if "mailtoboard" not in page.url:
            raise RuntimeError(
                "게시판 등록 페이지(mailtoboard/.../new)로 이동하지 못했습니다."
            ) from None


def _select_board_on_postwrite(page, board_name: str) -> None:
    esc = board_name.replace("\\", "\\\\").replace("'", "\\'")
    locators = [
        page.locator(f'div[data-testid="item-board-option"][title="{board_name}"]'),
        page.locator('[data-testid="item-board-option"]', has_text=board_name),
        page.locator(f"div[title='{esc}']"),
        page.get_by_text(board_name, exact=True),
    ]
    custom = (os.getenv("HIWORKS_MAIL_POST_BOARD_SELECTOR") or "").strip()
    if custom:
        for sel in (s.strip() for s in custom.split(",") if s.strip()):
            locators.insert(0, page.locator(sel.replace("{board}", board_name)))

    if not _click_first(page, locators, timeout=15_000):
        raise RuntimeError(
            f"게시판 '{board_name}' 을(를) 선택하지 못했습니다. "
            "HIWORKS_BOARD_NAME 또는 HIWORKS_MAIL_POST_BOARD_SELECTOR 를 확인하세요."
        )
    page.wait_for_timeout(600)


def _submit_mail_to_board(page) -> None:
    locators = [
        page.locator('button[data-testid="btn-post-submit"]'),
        page.get_by_role("button", name="확인"),
        page.locator("button:has-text('확인')"),
    ]
    custom = (os.getenv("HIWORKS_MAIL_POST_SUBMIT_SELECTOR") or "").strip()
    if custom:
        locators.insert(0, page.locator(custom))

    if not _click_first(page, locators, timeout=15_000):
        raise RuntimeError(
            "게시 '확인' 버튼을 찾지 못했습니다. "
            "HIWORKS_MAIL_POST_SUBMIT_SELECTOR 를 확인하세요."
        )
    page.wait_for_timeout(2500)


def post_current_mail_view_to_board(page, board_name: str | None = None) -> None:
    board_name = board_name or _board_name_from_env()
    page.wait_for_timeout(1200)
    if not wait_for_mail_ui(page, timeout_ms=20_000):
        raise RuntimeError(
            "메일 읽기 화면이 아닙니다 ('다른 작업' 메뉴 없음). "
            f"현재 URL: {page.url}"
        )

    _open_mail_to_board_flow(page)
    if needs_login(page):
        raise RuntimeError("게시판 등록 화면 진입 전 로그인이 필요합니다.")

    _select_board_on_postwrite(page, board_name)
    _submit_mail_to_board(page)


def post_mails_via_menu(
    pending: list[InboundMail],
    on_each_success: Callable[[InboundMail], None] | None = None,
) -> None:
    if not pending:
        return

    headless = os.getenv("HIWORKS_PLAYWRIGHT_HEADLESS", "0").strip() in ("1", "true", "yes")
    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    board_name = _board_name_from_env()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            locale="ko-KR",
        )
        attach_dialog_auto_dismiss(context)
        page = context.pages[0] if context.pages else context.new_page()

        for mail in pending:
            mail_url = (mail.pop_uid or "").strip()
            if not mail_url.startswith("http"):
                raise RuntimeError(
                    f"웹메일 URL이 없습니다 (POP3만으로는 게시 불가): {mail.subject}"
                )

            page.goto(mail_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1500)

            if needs_login(page):
                context.close()
                print(
                    "하이웍스 웹메일 로그인 세션이 없습니다.\n"
                    "  python src/setup_hiworks_browser.py 실행 후 OTP 로그인을 완료하세요."
                )
                sys.exit(2)

            post_current_mail_view_to_board(page, board_name)
            if on_each_success:
                on_each_success(mail)

        context.close()
