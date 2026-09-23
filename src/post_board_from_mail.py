"""PC 전용: [보안뉴스] 수신 메일을 하이웍스 게시판에 등록."""
import os
import sys
from datetime import datetime

from env_loader import ENV_FILE, PROJECT_ROOT, load_project_env
from mail_inbox import fetch_security_news_mails

BOARD_POSTED_UIDS = PROJECT_ROOT / "board_posted_uids.txt"
SUBJECT_TAG = "[보안뉴스]"


def load_posted_uids() -> set[str]:
    if not BOARD_POSTED_UIDS.is_file():
        return set()
    return {
        line.strip()
        for line in BOARD_POSTED_UIDS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def save_posted_uids(uids: set[str]) -> None:
    BOARD_POSTED_UIDS.write_text(
        "\n".join(sorted(uids)) + ("\n" if uids else ""),
        encoding="utf-8",
    )


def _mail_fetch_mode() -> str:
    mode = (os.getenv("HIWORKS_MAIL_FETCH") or "auto").strip().lower()
    list_url = (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip()
    if mode == "auto":
        return "web" if list_url else "pop3"
    return mode


def _post_method() -> str:
    method = (os.getenv("HIWORKS_POST_METHOD") or "auto").strip().lower()
    if method == "auto":
        if (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip():
            return "board_form"
        return "board_form"
    return method


def validate_env(mode: str, post_method: str) -> tuple[str, str]:
    missing = []
    if post_method == "board_form":
        if not (os.getenv("HIWORKS_BOARD_WRITE_URL") or "").strip():
            missing.append("HIWORKS_BOARD_WRITE_URL")
    elif post_method == "mail_menu":
        if not (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip():
            missing.append("HIWORKS_MAIL_LIST_URL")
    if mode in ("pop3", "both"):
        user = (os.getenv("HIWORKS_SMTP_USER") or os.getenv("HIWORKS_POP3_USER") or "").strip()
        password = (
            os.getenv("HIWORKS_SMTP_PASS") or os.getenv("HIWORKS_POP3_PASS") or ""
        ).strip()
        if not user:
            missing.append("HIWORKS_SMTP_USER (또는 HIWORKS_POP3_USER)")
        if not password:
            missing.append("HIWORKS_SMTP_PASS (또는 HIWORKS_POP3_PASS)")
    else:
        user = (os.getenv("HIWORKS_SMTP_USER") or "").strip()
        password = ""
        if not (os.getenv("HIWORKS_MAIL_LIST_URL") or "").strip():
            missing.append("HIWORKS_MAIL_LIST_URL")

    if post_method in ("board_form", "mail_menu") and mode == "pop3":
        missing.append("HIWORKS_MAIL_FETCH=web")

    if missing:
        print("오류: .env 에 다음이 필요합니다:", ", ".join(missing))
        print(f"  경로: {ENV_FILE}")
        sys.exit(1)
    return user, password


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    load_project_env()
    mode = _mail_fetch_mode()
    post_method = _post_method()
    user, password = validate_env(mode, post_method)
    posted = load_posted_uids()
    dry_run = "--dry-run" in sys.argv

    _log(f"메일 수집: {mode} / 게시: {post_method}")

    use_web_pipeline = mode == "web" and post_method in ("board_form", "mail_menu")

    if use_web_pipeline:
        from mail_inbox_web import run_web_mail_board_pipeline

        write_url = (os.getenv("HIWORKS_BOARD_WRITE_URL") or "").strip()
        if post_method == "mail_menu":
            from hiworks_mail_post import post_mails_via_menu as _legacy

            _log("HIWORKS_POST_METHOD=mail_menu (레거시). board_form 권장.")
        else:
            _log(f"웹메일 한 세션: 목록 → 본문 → 글쓰기 ({write_url})")

        def _mark_posted(mail) -> None:
            posted.add(mail.pop_uid)
            save_posted_uids(posted)
            print(f"게시 완료: {mail.subject}")

        if post_method == "mail_menu":
            try:
                from mail_inbox_web import fetch_security_news_mails_web

                mails = fetch_security_news_mails_web(subject_tag=SUBJECT_TAG)
                pending = [m for m in mails if m.pop_uid not in posted]
                if dry_run:
                    for mail in pending:
                        print(f"  [dry-run] uid={mail.pop_uid} | {mail.subject}")
                    return
                _legacy(pending, on_each_success=_mark_posted)
            except SystemExit:
                raise
            except Exception as e:
                _log(f"오류: {e}")
                sys.exit(1)
            return

        try:
            pending = run_web_mail_board_pipeline(
                SUBJECT_TAG,
                posted,
                dry_run=dry_run,
                on_each_success=None if dry_run else _mark_posted,
            )
        except SystemExit:
            raise
        except Exception as e:
            _log(f"오류: {e}")
            sys.exit(1)

        if dry_run:
            _log(f"[보안뉴스] 미게시 {len(pending)}통")
            for mail in pending:
                print(f"  [dry-run] uid={mail.pop_uid} | {mail.subject}")
        elif not pending:
            _log("게시할 새 [보안뉴스] 메일 없음")
        return

    _log("POP3 경로는 board_form + post_to_board (별도 브라우저) 입니다.")
    try:
        mails = fetch_security_news_mails(user, password, subject_tag=SUBJECT_TAG)
    except Exception as e:
        _log(f"메일 수집 오류: {e}")
        sys.exit(1)

    pending = [m for m in mails if m.pop_uid not in posted]
    if not pending:
        _log("게시할 새 [보안뉴스] 메일 없음")
        sys.exit(0)
    if dry_run:
        for mail in pending:
            print(f"  [dry-run] uid={mail.pop_uid} | {mail.subject}")
        return

    from hiworks_board import post_to_board

    for mail in pending:
        body = mail.text_body or mail.subject
        post_to_board(mail.subject, body)
        posted.add(mail.pop_uid)
        save_posted_uids(posted)
        print(f"게시 완료: {mail.subject}")


if __name__ == "__main__":
    main()
