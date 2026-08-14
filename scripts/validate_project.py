#!/usr/bin/env python3
"""Check that the Voice of Customer project scaffolding, pipeline scripts,
and data files exist and have the required fields."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = ["scripts", "data", "output"]

REQUIRED_SCRIPTS = [
    "collect_reviews.py",
    "collect_marketing.py",
    "find_themes.py",
    "find_gaps.py",
    "vocab_gap.py",
    "build_dashboard.py",
    "prepare_marketing_insights.py",
    "build_marketing_dashboard.py",
    "validate_project.py",
]

# Each entry: relative path -> (top_level_fields, list_field, item_fields)
# list_field/item_fields are None when the file has no nested list to check.
DATA_FILES = {
    "data/reviews.json": (
        ["game_name", "source_url", "app_id", "review_count", "reviews"],
        "reviews",
        ["review_id", "text", "recommended", "date"],
    ),
    "data/marketing.json": (
        ["game_name", "source_url", "claims"],
        "claims",
        ["claim_id", "text"],
    ),
    "data/review_themes.json": (
        ["game_name", "themes"],
        "themes",
        [
            "theme_id",
            "theme",
            "sentiment",
            "mention_count",
            "keywords",
            "example_review_ids",
            "quotes",
        ],
    ),
    "data/gaps.json": (
        ["hidden_strengths", "marketing_disconnects"],
        None,
        None,
    ),
    "data/vocabulary.json": (
        ["review_only_terms", "marketing_only_terms", "same_idea_different_words"],
        None,
        None,
    ),
    "data/marketing_insights.json": (
        ["game_name", "source_url", "app_id", "model", "perceptions", "top_recommendations"],
        "perceptions",
        [
            "perception_id",
            "theme_id",
            "customer_perception",
            "current_marketing_position",
            "alignment",
            "recommended_action",
            "suggested_messaging",
            "evidence_quote",
            "evidence_review_id",
        ],
    ),
}

OUTPUT_FILES = ["output/dashboard.html", "output/marketing_dashboard.html"]


def check_directories():
    results = []
    for name in REQUIRED_DIRS:
        results.append((name, (ROOT / name).is_dir()))
    return results


def check_scripts():
    results = []
    for name in REQUIRED_SCRIPTS:
        results.append((f"scripts/{name}", (ROOT / "scripts" / name).is_file()))
    return results


def check_data_file(rel_path, top_level_fields, list_field, item_fields):
    path = ROOT / rel_path
    if not path.is_file():
        return "missing", []

    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        return "invalid", [f"not valid JSON: {e}"]

    errors = []
    for field in top_level_fields:
        if field not in payload:
            errors.append(f"missing top-level field '{field}'")

    if list_field and list_field in payload:
        items = payload[list_field]
        if not isinstance(items, list):
            errors.append(f"'{list_field}' must be a list")
        else:
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"'{list_field}[{i}]' must be an object")
                    continue
                for field in item_fields:
                    if field not in item:
                        errors.append(f"'{list_field}[{i}]' missing field '{field}'")

    return ("ok" if not errors else "invalid"), errors


def check_output_files():
    results = []
    for rel_path in OUTPUT_FILES:
        results.append((rel_path, (ROOT / rel_path).is_file()))
    return results


def main():
    hard_failures = []

    print("== Directories ==")
    for name, ok in check_directories():
        print(f"  [{'OK' if ok else 'MISSING'}] {name}/")
        if not ok:
            hard_failures.append(f"missing required directory: {name}/")

    print("\n== Pipeline scripts ==")
    for name, ok in check_scripts():
        print(f"  [{'OK' if ok else 'MISSING'}] {name}")

    print("\n== Data files ==")
    for rel_path, (top_level_fields, list_field, item_fields) in DATA_FILES.items():
        status, errors = check_data_file(rel_path, top_level_fields, list_field, item_fields)
        if status == "missing":
            print(f"  [MISSING] {rel_path} (not generated yet)")
        elif status == "ok":
            print(f"  [OK] {rel_path}")
        else:
            print(f"  [INVALID] {rel_path}")
            for err in errors:
                print(f"      - {err}")
                hard_failures.append(f"{rel_path}: {err}")

    print("\n== Output files ==")
    for rel_path, ok in check_output_files():
        print(f"  [{'OK' if ok else 'MISSING'}] {rel_path}{'' if ok else ' (not generated yet)'}")

    print()
    if hard_failures:
        print(f"FAIL: {len(hard_failures)} structural problem(s) found.")
        return 1

    print("PASS: no structural problems. Missing pipeline outputs above are expected until generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
