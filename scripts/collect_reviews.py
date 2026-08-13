#!/usr/bin/env python3
"""Collect real Steam player reviews for a game and write data/reviews.json.

Usage:
    python scripts/collect_reviews.py <steam_store_url> <game_name> [--max-reviews N]

Example:
    python scripts/collect_reviews.py \
        https://store.steampowered.com/app/252490 "Rust"

Uses Steam's public appreviews endpoint (no API key required) and paginates
with the cursor it returns until the requested number of reviews has been
collected or Steam has no more reviews to give. Never fabricates or mocks
review data — if Steam cannot be reached, the script stops and reports the
real error.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "data" / "reviews.json"

REVIEWS_ENDPOINT = "https://store.steampowered.com/appreviews/{app_id}"
REVIEWS_PER_PAGE = 100
USER_AGENT = "VoiceOfCustomer/1.0 (review collector; +https://github.com/)"


def extract_app_id(url: str) -> str:
    match = re.search(r"/app/(\d+)", url)
    if not match:
        raise ValueError(f"Could not extract a Steam App ID from URL: {url}")
    return match.group(1)


def fetch_review_page(app_id: str, cursor: str) -> dict:
    params = {
        "json": "1",
        "filter": "recent",
        "language": "english",
        "review_type": "all",
        "purchase_type": "all",
        "num_per_page": str(REVIEWS_PER_PAGE),
        "cursor": cursor,
    }
    url = REVIEWS_ENDPOINT.format(app_id=app_id) + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Steam API HTTP error {e.code}: {e.reason} (url={url})") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Steam API: {e.reason} (url={url})") from e

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Steam API returned invalid JSON: {e}") from e

    if payload.get("success") != 1:
        raise RuntimeError(f"Steam API reported failure for app_id={app_id}: {payload}")

    return payload


def collect_reviews(app_id: str, max_reviews: int) -> list:
    reviews = []
    seen_ids = set()
    cursor = "*"

    while len(reviews) < max_reviews:
        payload = fetch_review_page(app_id, cursor)
        raw_reviews = payload.get("reviews", [])

        if not raw_reviews:
            break

        for raw in raw_reviews:
            review_id = str(raw.get("recommendationid"))
            if review_id in seen_ids:
                continue
            seen_ids.add(review_id)
            reviews.append(
                {
                    "review_id": review_id,
                    "text": raw.get("review", ""),
                    "recommended": bool(raw.get("voted_up")),
                    "date": raw.get("timestamp_created"),
                }
            )
            if len(reviews) >= max_reviews:
                break

        next_cursor = payload.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return reviews


def main():
    parser = argparse.ArgumentParser(description="Collect real Steam reviews into data/reviews.json")
    parser.add_argument("url", help="Steam store URL for the game, e.g. https://store.steampowered.com/app/252490")
    parser.add_argument("game_name", help="Human-readable game name, e.g. Rust")
    parser.add_argument("--max-reviews", type=int, default=1000, help="Maximum number of reviews to collect (default 1000)")
    args = parser.parse_args()

    try:
        app_id = extract_app_id(args.url)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        reviews = collect_reviews(app_id, args.max_reviews)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not reviews:
        print("ERROR: No reviews were collected from Steam. Refusing to write mock data.", file=sys.stderr)
        sys.exit(1)

    output = {
        "game_name": args.game_name,
        "source_url": args.url,
        "app_id": app_id,
        "review_count": len(reviews),
        "reviews": reviews,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Collected {len(reviews)} real reviews for '{args.game_name}' (app_id={app_id})")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
