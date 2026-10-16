"""Evidence-linked rescue for custom-font fields using public Fanqie book details.

This is *not* private-font glyph decoding. A title may be recovered only by
following the ranking's genuine numeric book URL to a matching first-party
detail page, checking a real Unicode heading and title in that same page.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


BOOK_LINK = re.compile(r"^/page/[0-9]{9,21}$")
BASE = "https://fanqienovel.com"


def detail_metadata(page: Any, href: str, timeout_ms: int = 22000) -> dict[str, str]:
    if not BOOK_LINK.fullmatch(href):
        raise ValueError("FANQIE_DETAIL_INVALID_BOOK_ID")
    url = BASE + href
    # browser.new_page() owns its context; use a separate browser-owned tab.
    browser = getattr(page.context, "browser", None)
    tab = browser.new_page() if browser is not None else page.context.new_page()
    try:
        tab.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if urlsplit(tab.url).scheme != "https" or tab.url.rstrip("/") != url:
            raise ValueError("FANQIE_DETAIL_REDIRECT_OR_MISMATCH")
        raw = tab.evaluate("""() => ({
            url:location.origin+location.pathname,
            title:document.title,
            heading:document.querySelector('h1')?.innerText?.trim()||'',
            description:document.querySelector('meta[name="description"]')?.content||''
        })""")
    finally:
        tab.close()
    heading = str(raw.get("heading") or "").strip()
    document_title = str(raw.get("title") or "")
    if not heading or len(heading) > 120 or heading not in document_title:
        raise ValueError("FANQIE_DETAIL_TITLE_UNVERIFIED")
    if any(
        ord(char) == 0xFFFD or 0xE000 <= ord(char) <= 0xF8FF
        for char in heading
    ):
        raise ValueError("FANQIE_DETAIL_TITLE_STILL_OBFUSCATED")
    return {
        "title": heading,
        "description": str(raw.get("description") or ""),
        "evidence_url": url,
        "book_id": href.rsplit("/", 1)[1],
    }
