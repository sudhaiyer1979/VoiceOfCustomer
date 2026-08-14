#!/usr/bin/env python3
"""Voice of Customer - WS8: Marketing Insights.

Turns the real customer review / marketing / theme / gap / vocabulary data
already produced by the earlier pipeline stages into marketer-facing brand
perception insights, using Claude as a senior brand strategist.

Usage:
    ANTHROPIC_API_KEY=... python scripts/prepare_marketing_insights.py

Reads (all from data/, must already exist -- run collect_reviews.py,
collect_marketing.py, find_themes.py, find_gaps.py and vocab_gap.py first):
    data/reviews.json
    data/marketing.json
    data/review_themes.json
    data/gaps.json
    data/vocabulary.json

Output (exactly one file):
    data/marketing_insights.json

Grounding guarantee: Claude is given only real theme quotes (each paired
with the review_id it came from), real marketing claims, and real
vocabulary terms. Every theme_id, evidence_review_id and evidence_quote
Claude returns is checked against that source data before the file is
written -- the script fails loudly if anything doesn't trace back.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT_PATH = DATA / "marketing_insights.json"

DEFAULT_MODEL = "claude-sonnet-5"

ALIGNMENTS = {"ALIGNED", "UNDERREPRESENTED", "OVEREMPHASIZED"}
ACTIONS = {"ADD", "KEEP", "REDUCE", "REFRAME"}

SYSTEM_PROMPT = """You are a senior brand strategist. You are given real \
player-review analysis (themes, quotes, marketing claims, gaps, vocabulary) \
for a video game, and you turn it into marketer-facing brand perception \
insights.

Turn machine-generated theme labels (e.g. "Friends & Solo & Wipe") into a \
plain-English customer perception sentence a marketer could read in a \
meeting (e.g. "Playing with friends creates memorable shared experiences.").

For every theme you cover, decide whether the current marketing is ALIGNED, \
UNDERREPRESENTED, or OVEREMPHASIZED relative to how much players actually \
talk about it, give a recommended action, and a suggested messaging \
direction.

You must ONLY use the theme_id / review_id / quote values given to you in \
the data below -- never invent a quote, a statistic, or an id. Every \
evidence_quote you write must be copied verbatim from the quotes list of \
the theme it's attached to, and evidence_review_id must be the review_id \
paired with that exact quote."""

USER_INSTRUCTIONS = """Here is the real customer review, marketing, theme, \
gap and vocabulary data for this game:

{context}

Produce:
1. "perceptions": one entry per theme worth covering (skip thin themes), \
each with a human-readable customer_perception sentence (never the raw \
theme label), current_marketing_position, alignment \
(ALIGNED/UNDERREPRESENTED/OVEREMPHASIZED), recommended_action, \
suggested_messaging, and grounded evidence_quote + evidence_review_id.
2. "top_recommendations": 3-5 recommendations, each using ADD, KEEP, \
REDUCE, or REFRAME as the action, with a short title and a one or two \
sentence detail.

Ground every evidence_quote and evidence_review_id in the data given above; \
do not invent any."""


def load(name):
    path = DATA / name
    if not path.is_file():
        raise RuntimeError(
            f"{path} not found. Run the earlier pipeline stages first "
            "(collect_reviews.py, collect_marketing.py, find_themes.py, "
            "find_gaps.py, vocab_gap.py)."
        )
    with path.open() as f:
        return json.load(f)


def build_context(reviews, marketing, themes, gaps, vocab):
    theme_context = []
    for t in themes["themes"]:
        quotes = t.get("quotes", [])
        review_ids = t.get("example_review_ids", [])
        theme_context.append({
            "theme_id": t["theme_id"],
            "theme_label": t["theme"],
            "sentiment": t["sentiment"],
            "mention_count": t["mention_count"],
            "keywords": t.get("keywords", []),
            "quotes": [
                {"review_id": rid, "quote": q}
                for q, rid in zip(quotes, review_ids)
            ],
        })

    claims = [
        {"claim_id": c["claim_id"], "text": c["text"]}
        for c in marketing.get("claims", [])
    ]

    return {
        "game_name": reviews.get("game_name"),
        "review_count": reviews.get("review_count"),
        "themes": theme_context,
        "marketing_claims": claims,
        "hidden_strengths": gaps.get("hidden_strengths", []),
        "marketing_disconnects": gaps.get("marketing_disconnects", []),
        "review_only_terms": vocab.get("review_only_terms", [])[:15],
        "marketing_only_terms": vocab.get("marketing_only_terms", [])[:15],
        "same_idea_different_words": vocab.get("same_idea_different_words", []),
    }


def build_tool():
    return {
        "name": "submit_marketing_insights",
        "description": (
            "Submit the finished brand perception insights: per-theme "
            "customer perceptions plus a short list of top recommendations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "perceptions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "theme_id": {
                                "type": "string",
                                "description": "One of the theme_id values given in the data.",
                            },
                            "customer_perception": {
                                "type": "string",
                                "description": "Human-readable statement of how customers see this, not the raw theme label.",
                            },
                            "current_marketing_position": {"type": "string"},
                            "alignment": {
                                "type": "string",
                                "enum": sorted(ALIGNMENTS),
                            },
                            "recommended_action": {"type": "string"},
                            "suggested_messaging": {"type": "string"},
                            "evidence_quote": {
                                "type": "string",
                                "description": "Copied verbatim from that theme's quotes list.",
                            },
                            "evidence_review_id": {
                                "type": "string",
                                "description": "The review_id paired with evidence_quote in that theme's quotes list.",
                            },
                        },
                        "required": [
                            "theme_id",
                            "customer_perception",
                            "current_marketing_position",
                            "alignment",
                            "recommended_action",
                            "suggested_messaging",
                            "evidence_quote",
                            "evidence_review_id",
                        ],
                    },
                },
                "top_recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": sorted(ACTIONS)},
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["action", "title", "detail"],
                    },
                },
            },
            "required": ["perceptions", "top_recommendations"],
        },
    }


def call_claude(context, model):
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it and try again."
        )

    client = anthropic.Anthropic(api_key=api_key)
    tool = build_tool()
    message = USER_INSTRUCTIONS.format(context=json.dumps(context, indent=2, ensure_ascii=False))

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_marketing_insights"},
        messages=[{"role": "user", "content": message}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_marketing_insights":
            return block.input

    raise RuntimeError("Claude did not return structured marketing insights.")


def verify(insights, themes_by_id):
    errors = []

    for p in insights.get("perceptions", []):
        theme_id = p.get("theme_id")
        theme = themes_by_id.get(theme_id)
        if theme is None:
            errors.append(f"unknown theme_id {theme_id!r}")
            continue
        if p.get("alignment") not in ALIGNMENTS:
            errors.append(f"{theme_id}: invalid alignment {p.get('alignment')!r}")

        pairs = list(zip(theme.get("quotes", []), theme.get("example_review_ids", [])))
        if (p.get("evidence_quote"), p.get("evidence_review_id")) not in pairs:
            errors.append(
                f"{theme_id}: evidence_quote/evidence_review_id doesn't match a "
                "real (quote, review_id) pair for that theme"
            )

    for r in insights.get("top_recommendations", []):
        if r.get("action") not in ACTIONS:
            errors.append(f"invalid recommendation action {r.get('action')!r}")

    return errors


def main():
    try:
        reviews = load("reviews.json")
        marketing = load("marketing.json")
        themes = load("review_themes.json")
        gaps = load("gaps.json")
        vocab = load("vocabulary.json")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    context = build_context(reviews, marketing, themes, gaps, vocab)

    try:
        insights = call_claude(context, model)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    themes_by_id = {t["theme_id"]: t for t in themes["themes"]}
    errors = verify(insights, themes_by_id)
    if errors:
        print("ERROR: Claude referenced data that doesn't trace back to the source files:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    perceptions = insights["perceptions"]
    recommendations = insights["top_recommendations"]

    for i, p in enumerate(perceptions, start=1):
        p["perception_id"] = f"I{i:03d}"
    for i, r in enumerate(recommendations, start=1):
        r["recommendation_id"] = f"R{i:03d}"

    output = {
        "game_name": reviews.get("game_name"),
        "source_url": reviews.get("source_url", ""),
        "app_id": str(reviews.get("app_id", "")),
        "model": model,
        "perceptions": perceptions,
        "top_recommendations": recommendations,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(perceptions)} customer perceptions and {len(recommendations)} recommendations")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
