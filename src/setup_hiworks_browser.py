"""하이웍스 브라우저 세션 저장 (OTP 후 편지함 자동 감지, Enter 불필요)."""
import os
import sys
import time

from env_loader import load_project_env
from playwright.sync_api import sync_playwright

from hiworks_board import _profile_dir, attach_dialog_auto_dismiss, try_prefill_login_id
from hiworks_session import (
    ensure_mail_session_or_exit,
    mail_list_ready,
    needs_login,
    pick_mail_page,
)


def _safe_close(context) -> None:
    try:
        context.close()
    except Exception:
        pass


def main() -> None:
    load_project_env()
    home = (os.getenv("HIWORKS_OFFICE_HOME") or "").strip()
    mail_list = (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip()
    if not mail_list and not home:
        print("HIWORKS_MAIL_LIST_URL 또는 HIWORKS_OFFICE_HOME 이 필요합니다.")
        sys.exit(1)

    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    print(f"브라우저 프로필: {profile}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            locale="ko-KR",
        )
        attach_dialog_auto_dismiss(context)
        page = context.pages[0] if context.pages else context.new_page()

        if mail_list:
            page = ensure_mail_session_or_exit(page, mail_list)
        else:
            page.goto(home, wait_until="domcontentloaded", timeout=60_000)
            if needs_login(page):
                try_prefill_login_id(page)
            from hiworks_session import wait_until_mail_session

            ok, page = wait_until_mail_session(page, home, timeout_sec=600)
            if not ok:
                _safe_close(context)
                sys.exit(1)

        page = pick_mail_page(page.context, page) or page
        if mail_list and not mail_list_ready(page):
            print(f"편지함 확인 실패: {page.url}", flush=True)
            _safe_close(context)
            sys.exit(1)

        print("세션 저장 중… (브라우저 창이 닫힙니다)", flush=True)
        time.sleep(0.5)
        _safe_close(context)

    print("세션 저장 완료.")


if __name__ == "__main__":
    main()
