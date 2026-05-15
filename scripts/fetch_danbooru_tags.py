#!/usr/bin/env python3
"""Fetch Danbooru tags and generate CSV/autocomplete files."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import requests


API_URL = "https://danbooru.donmai.us/tags.json"
WIKI_PAGES_URL = "https://danbooru.donmai.us/wiki_pages.json"
USER_AGENT = "danbooru-tag-auto-updater/1.0"
LIMIT = 1000
MIN_COUNT = 20
REQUEST_DELAY_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
CSV_PATH = DATA_DIR / "danbooru_tags.csv"
AUTOCOMPLETE_PATH = DATA_DIR / "autocomplete.txt"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be 0 or greater")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Danbooru tags and write ComfyUI-compatible tag files."
    )
    parser.add_argument(
        "--min-count",
        type=positive_int,
        default=int(os.getenv("MIN_COUNT", MIN_COUNT)),
        help=f"minimum post_count to save (default: env MIN_COUNT or {MIN_COUNT})",
    )
    parser.add_argument(
        "--max-pages",
        type=positive_int,
        default=int(os.getenv("MAX_PAGES", "0")),
        help="optional page limit for testing; 0 means fetch until Danbooru returns []",
    )
    parser.add_argument(
        "--max-wiki-pages",
        type=positive_int,
        default=int(os.getenv("MAX_WIKI_PAGES", "0")),
        help="optional wiki page limit for testing; 0 means fetch until all aliases are checked",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=float(os.getenv("REQUEST_DELAY_SECONDS", REQUEST_DELAY_SECONDS)),
        help=f"delay between requests in seconds (default: {REQUEST_DELAY_SECONDS})",
    )
    return parser.parse_args()


def fetch_page(session: requests.Session, page: int) -> list[dict]:
    params = {
        "limit": LIMIT,
        "search[hide_empty]": "yes",
        "search[is_deprecated]": "no",
        "search[order]": "count",
        "page": page,
    }

    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                API_URL,
                headers={"User-Agent": USER_AGENT},
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            break
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(attempt)

    if response is None:
        raise RuntimeError(f"No response returned for page {page}")

    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected API response for page {page}: {data!r}")
    return data


def fetch_wiki_page(session: requests.Session, page: int) -> list[dict]:
    params = {
        "limit": LIMIT,
        "search[hide_deleted]": "yes",
        "page": page,
    }

    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                WIKI_PAGES_URL,
                headers={"User-Agent": USER_AGENT},
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            break
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(attempt)

    if response is None:
        raise RuntimeError(f"No response returned for wiki page {page}")

    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected wiki API response for page {page}: {data!r}")
    return data


def normalize_tag(raw: dict) -> dict | None:
    name = raw.get("name")
    category = raw.get("category")
    count = raw.get("post_count")

    if not isinstance(name, str) or not name:
        return None
    if not isinstance(category, int):
        return None
    if not isinstance(count, int):
        return None

    return {
        "tag": name,
        "category": category,
        "count": count,
        "alias": "",
    }


def normalize_aliases(raw: object) -> str:
    if isinstance(raw, list):
        names = [name for name in raw if isinstance(name, str) and name]
        return ",".join(dict.fromkeys(names))
    if isinstance(raw, str):
        return raw
    return ""


def fetch_tags(min_count: int, max_pages: int, delay: float) -> list[dict]:
    tags: list[dict] = []

    with requests.Session() as session:
        page = 1
        while True:
            if max_pages and page > max_pages:
                break

            rows = fetch_page(session, page)
            if not rows:
                break

            kept_on_page = 0
            for row in rows:
                tag = normalize_tag(row)
                if tag is not None and tag["count"] >= min_count:
                    tags.append(tag)
                    kept_on_page += 1

            print(
                f"Fetched page {page}: {len(rows)} rows, "
                f"{kept_on_page} kept on page, {len(tags)} kept total",
                flush=True,
            )

            if kept_on_page == 0:
                print(
                    f"Stopping at page {page}: no tags met min_count={min_count}",
                    flush=True,
                )
                break

            page += 1

            if delay > 0:
                time.sleep(delay)

    tags.sort(key=lambda item: item["count"], reverse=True)
    return tags


def add_aliases(tags: list[dict], max_wiki_pages: int, delay: float) -> None:
    tags_by_name = {tag["tag"]: tag for tag in tags}
    remaining = set(tags_by_name)
    alias_count = 0

    with requests.Session() as session:
        page = 1
        while remaining:
            if max_wiki_pages and page > max_wiki_pages:
                break

            rows = fetch_wiki_page(session, page)
            if not rows:
                break

            matched_on_page = 0
            for row in rows:
                title = row.get("title")
                if not isinstance(title, str) or title not in remaining:
                    continue

                aliases = normalize_aliases(row.get("other_names"))
                if aliases:
                    tags_by_name[title]["alias"] = aliases
                    alias_count += 1

                remaining.remove(title)
                matched_on_page += 1

            print(
                f"Fetched wiki page {page}: {len(rows)} rows, "
                f"{matched_on_page} matched on page, {alias_count} aliases found",
                flush=True,
            )
            page += 1

            if delay > 0:
                time.sleep(delay)

    print(
        f"Filled aliases for {alias_count} tags; {len(remaining)} tags had no wiki match",
        flush=True,
    )


def write_csv(tags: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["tag", "category", "count", "alias"])
        writer.writeheader()
        writer.writerows(tags)


def write_autocomplete(tags: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for tag in tags:
            file.write(f"{tag['tag']},{tag['count']}\n")


def main() -> int:
    args = parse_args()
    tags = fetch_tags(
        min_count=args.min_count,
        max_pages=args.max_pages,
        delay=args.delay,
    )
    add_aliases(tags, args.max_wiki_pages, args.delay)

    write_csv(tags, CSV_PATH)
    write_autocomplete(tags, AUTOCOMPLETE_PATH)

    print(f"Wrote {len(tags)} tags to {CSV_PATH}", flush=True)
    print(f"Wrote {len(tags)} tags to {AUTOCOMPLETE_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as error:
        print(f"Danbooru request failed: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
