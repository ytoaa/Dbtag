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

            for row in rows:
                tag = normalize_tag(row)
                if tag is not None and tag["count"] >= min_count:
                    tags.append(tag)

            print(f"Fetched page {page}: {len(rows)} rows, {len(tags)} kept")
            page += 1

            if delay > 0:
                time.sleep(delay)

    tags.sort(key=lambda item: item["count"], reverse=True)
    return tags


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

    write_csv(tags, CSV_PATH)
    write_autocomplete(tags, AUTOCOMPLETE_PATH)

    print(f"Wrote {len(tags)} tags to {CSV_PATH}")
    print(f"Wrote {len(tags)} tags to {AUTOCOMPLETE_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as error:
        print(f"Danbooru request failed: {error}", file=sys.stderr)
        raise SystemExit(1)
