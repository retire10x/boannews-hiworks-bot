"""웹메일 읽기 화면 본문 추출 디버그."""
import json
import sys
from pathlib import Path

from env_loader import PROJECT_ROOT, load_project_env
from playwright.sync_api import sync_playwright

from hiworks_board import _profile_dir, attach_dialog_auto_dismiss
from hiworks_session import wait_for_mail_read_ui
from mail_inbox_web import _extract_body, _mail_chrome_score

load_project_env()
uids = Path(PROJECT_ROOT / "board_posted_uids.txt")
url = (uids.read_text(encoding="utf-8").splitlines() or [""])[-1].strip()
if not url.startswith("http"):
    print("board_posted_uids.txt 에 URL 이 없습니다.")
    sys.exit(1)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(_profile_dir()), headless=True, locale="ko-KR"
    )
    attach_dialog_auto_dismiss(ctx)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3000)
    print("URL:", page.url[:100])
    print("read_ui:", wait_for_mail_read_ui(page))
    info = page.evaluate(
        """() => {
        const iframes = [...document.querySelectorAll('iframe')].map((f, i) => ({
          i,
          cls: (f.className || '').slice(0, 60),
          id: f.id,
          src: (f.src || '').slice(0, 100),
          w: f.getBoundingClientRect().width,
          h: f.getBoundingClientRect().height,
        }));
        const hits = [];
        for (const el of document.querySelectorAll('div, section, article, iframe')) {
          const c = (el.className || '').toString().slice(0, 80);
          let t = '';
          try { t = (el.innerText || '').trim(); } catch (e) { continue; }
          if (t.length < 60) continue;
          const links = el.querySelectorAll('a[href^="http"]').length;
          hits.push({
            tag: el.tagName,
            cls: c,
            len: t.length,
            links,
            head: t.slice(0, 100),
            chrome: /받은편지함|상단메뉴|다른 작업/.test(t.slice(0, 400)),
          });
        }
        hits.sort((a, b) => b.links - a.links || b.len - a.len);
        return { iframes, top: hits.slice(0, 15) };
      }"""
    )
    print(json.dumps(info, ensure_ascii=False, indent=2))
    body, _ = _extract_body(page)
    print("--- extract len:", len(body), "chrome:", _mail_chrome_score(body))
    print(body[:1500])
    ctx.close()
