"""게시판 글쓰기·SmartEditor DOM 확인 (브라우저 창 표시, OTP 가능)."""
import json
import os
import sys

from env_loader import load_project_env
from playwright.sync_api import sync_playwright

from hiworks_board import (
    _profile_dir,
    attach_dialog_auto_dismiss,
    ensure_board_write_page,
    fill_board_write_form,
)


def main() -> None:
    load_project_env()
    os.environ["HIWORKS_PLAYWRIGHT_HEADLESS"] = "0"

    write_url = (os.getenv("HIWORKS_BOARD_WRITE_URL") or "").strip()
    if not write_url:
        print("HIWORKS_BOARD_WRITE_URL 이 필요합니다.")
        sys.exit(1)

    dry = "--fill-test" not in sys.argv
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(_profile_dir()),
            headless=False,
            locale="ko-KR",
        )
        attach_dialog_auto_dismiss(ctx)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = ensure_board_write_page(page, write_url)
        page.wait_for_timeout(3000)

        info = page.evaluate(
            """() => {
            const iframe = document.querySelector('iframe.se-contents-edit');
            const ir = iframe ? iframe.getBoundingClientRect() : null;
            return {
              url: location.href,
              iframe: ir ? { w: ir.width, h: ir.height } : null,
              ceCount: document.querySelectorAll('[contenteditable]').length,
            };
          }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))

        if "--fill-test" in sys.argv:
            fill_board_write_form(page, "[debug] 제목", "본문 테스트 (debug_board_editor --fill-test)")
            print("fill-test 완료 — 게시판에서 확인 후 창을 닫으세요.")
            input("Enter 로 종료… ")

        ctx.close()


if __name__ == "__main__":
    main()
