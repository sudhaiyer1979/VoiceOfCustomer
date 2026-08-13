#!/usr/bin/env python3
"""Collect real Steam marketing copy for a game and write data/marketing.json.

Usage:
    python scripts/collect_marketing.py <steam_store_url> <game_name>

Example:
    python scripts/collect_marketing.py \
        https://store.steampowered.com/app/252490 "Rust"

Uses Steam's public appdetails endpoint (no API key required) to retrieve the
official store description (short description and the detailed/about-the-game
copy), strips HTML/images/markup, and splits the remaining text into
individual claims. The appdetails response does not include navigation
chrome, player reviews, or system requirements (those live in separate
fields/pages that this script never reads), and any leftover Steam store
boilerplate headings are dropped by an explicit filter. Claim text is never
invented or rewritten -- each claim is verbatim text taken from Steam's
description fields. Never fabricates or mocks marketing data -- if Steam
cannot be reached, the script stops and reports the real error.
"""

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "data" / "marketing.json"

APPDETAILS_ENDPOINT = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "VoiceOfCustomer/1.0 (marketing collector; +https://github.com/)"

# Steam store boilerplate/navigation/heading text that can appear inside the
# description HTML but is not itself a marketing claim.
JUNK_LINES = {
    "about this game",
    "about this content",
    "key features",
    "features",
    "overview",
    "system requirements",
    "minimum",
    "recommended",
    "buy now",
    "read more",
    "read less",
    "recent reviews",
    "all reviews",
    "review type",
    "steam community",
    "mature content description",
    "the developers describe the content like this:",
}

# Tags whose closing (or self-closing) form should become a line break so
# list items and paragraphs don't get glued into one wall of text.
BLOCK_BREAK_TAGS = re.compile(
    r"</?(?:p|div|li|ul|ol|h[1-6]|br)\s*/?>",
    re.IGNORECASE,
)
ANY_TAG = re.compile(r"<[^>]+>")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def extract_app_id(url: str) -> str:
    match = re.search(r"/app/(\d+)", url)
    if not match:
        raise ValueError(f"Could not extract a Steam App ID from URL: {url}")
    return match.group(1)


def fetch_app_details(app_id: str) -> dict:
    params = {"appids": app_id, "l": "english"}
    url = APPDETAILS_ENDPOINT + "?" + urllib.parse.urlencode(params)
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

    entry = payload.get(app_id)
    if not entry or not entry.get("success"):
        raise RuntimeError(f"Steam API reported failure for app_id={app_id}: {payload}")

    data = entry.get("data")
    if not data:
        raise RuntimeError(f"Steam API returned no store data for app_id={app_id}")

    return data


def html_to_lines(fragment: str) -> list:
    """Convert a Steam description HTML fragment into plain-text lines,
    stripping tags/images while preserving paragraph and list breaks."""
    text = BLOCK_BREAK_TAGS.sub("\n", fragment)
    text = ANY_TAG.sub("", text)
    text = html.unescape(text)

    lines = []
    for raw_line in text.split("\n"):
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return lines


def lines_to_claims(lines: list) -> list:
    claims = []
    for line in lines:
        if line.lower().strip(": ") in JUNK_LINES:
            continue
        for sentence in SENTENCE_SPLIT.split(line):
            sentence = sentence.strip()
            if sentence and sentence.lower() not in JUNK_LINES:
                claims.append(sentence)
    return claims


def collect_claims(data: dict) -> list:
    claims = []
    seen = set()

    for field in ("short_description", "detailed_description", "about_the_game"):
        fragment = data.get(field) or ""
        if not fragment:
            continue
        for claim in lines_to_claims(html_to_lines(fragment)):
            key = claim.lower()
            if key in seen:
                continue
            seen.add(key)
            claims.append(claim)

    return claims


def main():
    parser = argparse.ArgumentParser(description="Collect real Steam marketing copy into data/marketing.json")
    parser.add_argument("url", help="Steam store URL for the game, e.g. https://store.steampowered.com/app/252490")
    parser.add_argument("game_name", help="Human-readable game name, e.g. Rust")
    args = parser.parse_args()

    try:
        app_id = extract_app_id(args.url)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = fetch_app_details(app_id)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    claim_texts = collect_claims(data)

    if not claim_texts:
        print("ERROR: No marketing claims were extracted from Steam. Refusing to write mock data.", file=sys.stderr)
        sys.exit(1)

    claims = [
        {"claim_id": f"M{i:03d}", "text": text}
        for i, text in enumerate(claim_texts, start=1)
    ]

    output = {
        "game_name": args.game_name,
        "source_url": args.url,
        "claims": claims,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Collected {len(claims)} real marketing claims for '{args.game_name}' (app_id={app_id})")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
