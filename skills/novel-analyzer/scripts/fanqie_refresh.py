#!/usr/bin/env python3
"""Fresh, resumable Fanqie collector with auditable per-category states."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_CONFIG = {
    "books_per_category": 10,
    "sleep_seconds": 5,
    "navigation_timeout_ms": 30000,
    "selector_timeout_ms": 8000,
    "rank_attempts": 3,
    "retry_backoff_seconds": 3,
}
RANKS = [
    (0, 1, "female", "new_ranks", 1139),
    (1, 1, "male", "new_ranks", 1139),
    (0, 2, "female", "read_ranks", 1139),
    (1, 2, "male", "read_ranks", 1139),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config(path: Path | None, regression: bool) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if regression:
        config["books_per_category"] = 6
    if path:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("config must be a JSON object")
        config.update(payload)
    if int(config["books_per_category"]) < 1:
        raise ValueError("books_per_category must be >= 1")
    if int(config["rank_attempts"]) < 1:
        raise ValueError("rank_attempts must be >= 1")
    if float(config["retry_backoff_seconds"]) < 0:
        raise ValueError("retry_backoff_seconds must be >= 0")
    return config


def load_decoder(legacy_script: Path) -> Callable[[str], str]:
    spec = importlib.util.spec_from_file_location("fanqie_legacy", legacy_script)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import decoder from {legacy_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decode_text


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def reconcile_resume(state: dict[str, Any], result: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]]:
    """Ignore state-only completion so a missing/truncated result is recollected."""
    rows = {
        row.get("name"): row
        for row in result.get("categories", [])
        if isinstance(row, dict) and row.get("name")
    }
    state_completed = set(state.get("completed", []))
    completed = {
        name
        for name in state_completed
        if name in rows and rows[name].get("status") == "success" and rows[name].get("books")
    }
    return completed, list(rows.values())


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def category_record(name: str, books: list[dict[str, Any]], status: str | None = None, error: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status or ("success" if books else "empty"),
        "books": books,
        "error": error,
    }


def replace_row(rows: list[dict[str, Any]], row: dict[str, Any]) -> None:
    rows[:] = [old for old in rows if old.get("name") != row.get("name")]
    rows.append(row)


EXTRACT_JS = r"""
() => {
  const bookMap = new Map();
  for (const link of document.querySelectorAll('a[href^="/page/"]')) {
    let node = link.parentElement;
    for (let depth = 0; node && depth < 7; depth++, node = node.parentElement) {
      if (node.querySelector('img') && node.innerText.includes('在读')) {
        if (!bookMap.has(link.getAttribute('href'))) bookMap.set(link.getAttribute('href'), node);
        break;
      }
    }
  }
  return Array.from(bookMap.values()).map(item => {
    const link = item.querySelector('a[href^="/page/"]');
    const image = item.querySelector('img');
    const titleNode = item.querySelector('h4, .title, h1') || link;
    const authorNode = item.querySelector('.author, .author-name, a[href^="/author-page/"]');
    const introNode = item.querySelector('.intro, .abstract, .desc');
    const reads = item.innerText.split('\n').find(line => line.includes('在读')) || '';
    return {
      title: (image && image.alt || titleNode && titleNode.innerText || '').trim(),
      author: (authorNode && authorNode.innerText || '').trim(),
      reads,
      intro: (introNode && introNode.innerText || '').trim(),
      cover: image && image.getAttribute('src') || '',
      url: link && link.getAttribute('href') || ''
    };
  });
}
"""


def normalize_books(
    raw: list[dict[str, Any]],
    decoder: Callable[[str], str],
    limit: int,
    *,
    detail_resolver: Callable[[str], dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Never guess an obfuscated glyph; cross-check the book's official detail."""
    books = []
    for item in raw[:limit]:
        href = str(item.get("url") or "")
        fields = {}
        unreadable = set()
        for name in ("title", "author", "reads", "intro"):
            try:
                fields[name] = decoder(item.get(name, "")).strip()
            except ValueError:
                fields[name] = ""
                unreadable.add(name)
        detail: dict[str, str] = {}
        if unreadable:
            if detail_resolver is None:
                raise ValueError("FANQIE_CUSTOM_FONT_NEEDS_VERIFIED_OFFICIAL_DETAIL")
            # Resolver validates that the URL belongs to the same official book ID.
            detail = detail_resolver(href)
            if not detail.get("title") or not detail.get("evidence_url"):
                raise ValueError("FANQIE_DETAIL_METADATA_INCOMPLETE")
        title = fields["title"] or detail.get("title", "")
        if not title or title == "未知" or "榜单说明" in title:
            continue
        reads = fields["reads"].replace("在读", "").replace(":", "").replace("：", "")
        book = {
            "title": title,
            "author": fields["author"] or "未知",
            "reads": reads or "未知",
            "intro": (fields["intro"] or detail.get("description", "")).replace("\n", " ").strip(),
            "cover": item.get("cover", ""),
            "url": href if href.startswith("http") else "https://fanqienovel.com" + href,
        }
        if detail:
            book["verified_detail_url"] = detail["evidence_url"]
            book["unreadable_rank_fields"] = sorted(unreadable)
            book["field_provenance"] = {
                name: "official_detail_heading" if name == "title" else
                "official_detail_description" if name == "intro" else
                "unknown_unreadable_rank_field"
                for name in unreadable
            }
            # Missing author/reader counts stay visibly unknown; do not infer them.
        books.append(book)
    return books


def collect_rank(page: Any, rank: tuple[int, int, str, str, int], output_dir: Path, config: dict[str, Any], decoder: Callable[[str], str]) -> dict[str, Any]:
    gender, rank_type, gender_name, type_name, seed = rank
    date_key = output_dir.name
    result_path = output_dir / f"fanqie_{gender_name}_{type_name}_{date_key}.json"
    state_path = output_dir / f"task_state_{gender_name}_{type_name}_{date_key}.json"
    state = read_json(state_path)
    existing = read_json(result_path)
    completed, rows = reconcile_resume(state, existing)
    pattern = f"{gender}_{rank_type}_"
    started_at = utc_now()
    errors: list[dict[str, str]] = []

    page.goto(
        f"https://fanqienovel.com/rank/{pattern}{seed}",
        wait_until="domcontentloaded",
        timeout=int(config["navigation_timeout_ms"]),
    )
    page.wait_for_selector('menu, [class*="rank"], [class*="category"]', timeout=int(config["selector_timeout_ms"]))
    categories = page.evaluate(
        "() => Array.from(document.querySelectorAll('a'))"
        f".filter(a => a.href.includes('/rank/{pattern}'))"
        ".map(a => ({name:a.innerText.trim(), href:a.getAttribute('href')}))"
    )
    unique = {item.get("name"): item for item in categories if item.get("name") and item.get("href")}
    from fanqie_detail_metadata import detail_metadata
    detail_cache: dict[str, dict[str, str]] = {}

    def get_verified_detail(href: str) -> dict[str, str]:
        if href not in detail_cache:
            detail_cache[href] = detail_metadata(
                page, href, timeout_ms=int(config["navigation_timeout_ms"])
            )
        return detail_cache[href]

    for name, category in unique.items():
        if name in completed:
            continue
        status = "parse_error"
        books: list[dict[str, Any]] = []
        error = None
        try:
            # Prefer the first-party menu click used by the verified older
            # collector, with a bounded validated-URL fallback.
            href = str(category["href"])
            if not href.startswith("/rank/" + pattern):
                raise ValueError("FANQIE_CATEGORY_LINK_MISMATCH")
            switched = False
            link = page.locator('a[href="' + href + '"]')
            if link.count():
                try:
                    link.first.click(timeout=int(config["selector_timeout_ms"]))
                    page.wait_for_url(
                        "**" + href, timeout=int(config["selector_timeout_ms"])
                    )
                    switched = True
                except Exception:
                    switched = False
            if switched:
                try:
                    page.wait_for_selector(
                        'a[href^="/page/"]', timeout=max(12000, int(config["selector_timeout_ms"]))
                    )
                except Exception:
                    # A SPA route can update its URL before book cards mount.
                    # Reload the exact verified first-party category and retry.
                    switched = False
            if not switched:
                page.goto(
                    "https://fanqienovel.com" + href,
                    wait_until="domcontentloaded",
                    timeout=int(config["navigation_timeout_ms"]),
                )
                page.wait_for_selector(
                    'a[href^="/page/"]', timeout=max(12000, int(config["selector_timeout_ms"]))
                )
            for _ in range(3):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                time.sleep(1)
            books = normalize_books(
                page.evaluate(EXTRACT_JS), decoder, int(config["books_per_category"]),
                detail_resolver=get_verified_detail,
            )
            status = "success" if books else "empty"
        except Exception as exc:  # Playwright exposes several environment-specific exception types.
            error = f"{type(exc).__name__}: {exc}"
            errors.append({"category": name, "error": error})
        row = category_record(name, books, status, error)
        replace_row(rows, row)
        if status == "success":
            completed.add(name)
        snapshot = {
            "date": datetime.now().astimezone().date().isoformat(),
            "rank_type": f"{gender_name}/{type_name}",
            "started_at": started_at,
            "updated_at": utc_now(),
            "categories": rows,
        }
        save_json(result_path, snapshot)
        save_json(state_path, {"completed": sorted(completed), "result_file": str(result_path.resolve()), "updated_at": utc_now()})
        time.sleep(float(config["sleep_seconds"]))

    valid_books = sum(len(row.get("books", [])) for row in rows if row.get("status") == "success")
    return {
        "gender": gender_name,
        "rank_type": type_name,
        "status": "success" if rows and not errors and all(row.get("status") == "success" for row in rows) else "degraded",
        "category_count": len(unique),
        "valid_category_count": sum(row.get("status") == "success" for row in rows),
        "valid_book_count": valid_books,
        "empty_categories": [row.get("name") for row in rows if row.get("status") == "empty"],
        "errors": errors + [
            {"category": row.get("name", "unknown"), "error": row.get("error") or row.get("status", "unknown")}
            for row in rows if row.get("status") not in {"success", "empty"}
        ],
        "result_file": str(result_path.resolve()),
        "started_at": started_at,
        "finished_at": utc_now(),
    }


def failed_rank_summary(rank: tuple[int, int, str, str, int], exc: Exception) -> dict[str, Any]:
    return {
        "gender": rank[2],
        "rank_type": rank[3],
        "status": "failed",
        "category_count": 0,
        "valid_category_count": 0,
        "valid_book_count": 0,
        "empty_categories": [],
        "errors": [{"error": f"{type(exc).__name__}: {exc}"}],
        "started_at": utc_now(),
        "finished_at": utc_now(),
    }


def collect_rank_with_retries(
    page_factory: Callable[[], Any],
    rank: tuple[int, int, str, str, int],
    output_dir: Path,
    config: dict[str, Any],
    decoder: Callable[[str], str],
    *,
    collector: Callable[..., dict[str, Any]] = collect_rank,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Retry a failed/degraded rank with a fresh page and resumable state."""
    attempts = int(config["rank_attempts"])
    backoff = float(config["retry_backoff_seconds"])
    history: list[dict[str, Any]] = []
    last_summary: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        page = None
        try:
            page = page_factory()
            last_summary = collector(page, rank, output_dir, config, decoder)
        except Exception as exc:
            last_summary = failed_rank_summary(rank, exc)
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
        history.append({
            "attempt": attempt,
            "status": last_summary.get("status"),
            "errors": last_summary.get("errors", []),
        })
        if last_summary.get("status") == "success":
            break
        if attempt < attempts and backoff:
            sleeper(backoff * attempt)
    assert last_summary is not None
    last_summary["attempt_count"] = len(history)
    last_summary["retry_history"] = history
    return last_summary


def resolve_optional_collector(explicit: Path | None) -> Path:
    """Use an operator-supplied, appropriately licensed collector without bundling it."""
    selected = explicit or os.environ.get("NOVEL_FANQIE_COLLECTOR", "")
    if not selected:
        return Path(__file__).with_name("fanqie_decoder.py")
    path = Path(selected)
    return path if path.is_absolute() else Path(__file__).resolve().parents[3] / path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--date", help="YYYYMMDD; defaults to local today")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--regression", action="store_true", help="Use six books/category unless config overrides it")
    parser.add_argument("--legacy-script", type=Path, help="optional authorized alternative decoder (or set NOVEL_FANQIE_COLLECTOR); defaults to conservative bundled decoder")
    parser.add_argument("--rank-attempts", type=int)
    parser.add_argument("--retry-backoff-seconds", type=float)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    date_key = args.date or datetime.now().astimezone().strftime("%Y%m%d")
    output_dir = args.output_root / date_key
    started_at = utc_now()
    summaries = []
    config = load_config(args.config, args.regression)
    if args.rank_attempts is not None:
        config["rank_attempts"] = args.rank_attempts
    if args.retry_backoff_seconds is not None:
        config["retry_backoff_seconds"] = args.retry_backoff_seconds
    if int(config["rank_attempts"]) < 1 or float(config["retry_backoff_seconds"]) < 0:
        raise ValueError("retry settings are invalid")
    try:
        from playwright.sync_api import sync_playwright

        decoder = load_decoder(resolve_optional_collector(args.legacy_script))
        with sync_playwright() as playwright:
            launch = {"headless": True}
            selected_chrome = os.environ.get("NOVEL_CHROMIUM_EXECUTABLE", "").strip()
            if selected_chrome:
                launch["executable_path"] = selected_chrome
            elif not os.environ.get("GITHUB_ACTIONS"):
                launch["channel"] = "chrome"
            browser = playwright.chromium.launch(**launch)
            for rank in RANKS:
                summaries.append(collect_rank_with_retries(
                    lambda: browser.new_page(user_agent="Mozilla/5.0 AppleWebKit/537.36 Chrome/120 Safari/537.36"),
                    rank,
                    output_dir,
                    config,
                    decoder,
                ))
            browser.close()
    except Exception as exc:
        summaries.append({
            "gender": "all", "rank_type": "all", "status": "not_run",
            "category_count": 0, "valid_category_count": 0, "valid_book_count": 0,
            "empty_categories": [], "errors": [{"error": f"{type(exc).__name__}: {exc}"}],
            "started_at": started_at, "finished_at": utc_now(),
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    collection = {
        "schema_version": 1,
        "platform": "fanqie",
        "date": date_key,
        "config": config,
        "started_at": started_at,
        "finished_at": utc_now(),
        "ranks": summaries,
        "rank_count": len(summaries),
        "valid_book_count": sum(item.get("valid_book_count", 0) for item in summaries),
        "empty_categories": [f"{item.get('gender')}/{item.get('rank_type')}:{name}" for item in summaries for name in item.get("empty_categories", [])],
        "errors": [error for item in summaries for error in item.get("errors", [])],
        "status": "success" if len(summaries) == 4 and all(item.get("status") == "success" for item in summaries) else "degraded",
    }
    save_json(output_dir / "collection_summary.json", collection)
    print(json.dumps(collection, ensure_ascii=False, indent=2))
    return 0 if collection["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
