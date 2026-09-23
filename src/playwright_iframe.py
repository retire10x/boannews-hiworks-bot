"""Playwright Locator(iframe) → Frame. content_frame 은 FrameLocator 속성이라 () 호출 불가."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Locator


def iframe_frame(loc: Locator, *, timeout_ms: int = 5000) -> Frame | None:
    try:
        handle = loc.element_handle(timeout=timeout_ms)
        if handle is None:
            return None
        return handle.content_frame()
    except Exception:
        return None
