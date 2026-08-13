#!/usr/bin/env python3
"""Compare player review themes against marketing claims.

Reads data/review_themes.json and data/marketing.json and writes
data/gaps.json containing:

- hidden_strengths: themes players value or praise that marketing text
  barely (or never) mentions.
- marketing_disconnects: marketing claims that player review themes
  rarely (or never) discuss.

Matching is done with lightweight token overlap (no external NLP
dependencies) between each theme's keywords/name and each claim's text,
so the script stays reusable across different games' data.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEMES_PATH = ROOT / "data" / "review_themes.json"
MARKETING_PATH = ROOT / "data" / "marketing.json"
OUTPUT_PATH = ROOT / "data" / "gaps.json"

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at",
    "for", "with", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "as", "by", "from",
    "you", "your", "i", "we", "they", "them", "he", "she", "his", "her",
    "will", "can", "not", "no", "do", "does", "did", "has", "have", "had",
    "if", "so", "than", "then", "there", "their", "what", "when", "which",
    "who", "whom", "all", "any", "more", "most", "other", "some", "such",
    "into", "over", "out", "up", "down", "about", "above", "after",
    "before", "between", "including", "include", "includes", "now",
    "new", "also", "throughout", "much", "many", "and much",
}

# Words/phrases that indicate genuine player praise inside a review quote.
# Matched as whole words/phrases (see quote_has_praise) to avoid substring
# false positives such as "fun" inside "refund" or "enjoyable" inside
# "unenjoyable".
POSITIVE_WORDS = [
    "love", "loved", "loves", "best", "awesome", "amazing", "fun",
    "great", "worth", "recommend", "chill", "friendly", "flawlessly",
    "smooth", "favorite", "favourite", "enjoy", "enjoyed", "enjoyable",
    "well together", "playable", "solid", "polished", "incredible",
    "fantastic", "perfect", "satisfying",
]

NEGATIONS = {"not", "no", "n't", "never", "without", "unless"}

# Minimum shared-vocabulary "coverage" a theme can have with marketing text
# before it's considered actively marketed rather than a hidden strength.
HIDDEN_STRENGTH_COVERAGE_CEILING = 0.30

# Claims with fewer significant tokens than this are section headers (e.g.
# "EXPLORE", "BUILD") rather than substantive claims, and are excluded from
# marketing-disconnect candidacy.
MIN_CLAIM_TOKENS = 2


def normalize(word):
    word = re.sub(r"[^a-z0-9]", "", word.lower())
    if len(word) > 4 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 4 and word.endswith("es"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


def tokenize(text):
    raw_words = re.findall(r"[a-zA-Z']+", text)
    tokens = set()
    for w in raw_words:
        norm = normalize(w)
        if len(norm) > 2 and norm not in STOPWORDS:
            tokens.add(norm)
    return tokens


def theme_vocab(theme):
    tokens = tokenize(theme["theme"])
    for kw in theme.get("keywords", []):
        norm = normalize(kw)
        if norm:
            tokens.add(norm)
    return tokens


def claim_vocab(claim):
    return tokenize(claim["text"])


def quote_has_praise(quote):
    lowered = quote.lower()
    for phrase in POSITIVE_WORDS:
        match = re.search(r"\b" + re.escape(phrase) + r"\b", lowered)
        if not match:
            continue
        preceding = lowered[max(0, match.start() - 25):match.start()]
        if any(neg in preceding for neg in NEGATIONS):
            continue
        return phrase
    return None


def find_praise_quote(theme):
    for quote in theme.get("quotes", []):
        phrase = quote_has_praise(quote)
        if phrase:
            return quote, phrase
    return None, None


def match_theme_to_claims(theme_tokens, claims_with_vocab):
    """Return list of (claim_id, shared_tokens) for claims sharing vocabulary."""
    matches = []
    for claim, vocab in claims_with_vocab:
        shared = theme_tokens & vocab
        if shared:
            matches.append((claim["claim_id"], shared))
    return matches


def marketing_coverage_ratio(theme_tokens, claim_matches):
    """Fraction of a theme's vocabulary that shows up anywhere in marketing text."""
    if not theme_tokens:
        return 0.0
    covered = set()
    for _claim_id, shared in claim_matches:
        covered |= shared
    return len(covered) / len(theme_tokens)


def match_claim_to_themes(claim_tokens, themes_with_vocab):
    """Return list of (theme_id, mention_count, shared_tokens) for related themes."""
    matches = []
    for theme, vocab in themes_with_vocab:
        shared = claim_tokens & vocab
        if shared:
            matches.append((theme["theme_id"], theme["mention_count"], shared))
    return matches


def find_hidden_strengths(themes, claims_with_vocab, limit=5):
    themes_with_vocab = [(t, theme_vocab(t)) for t in themes]
    candidates = []

    for theme, vocab in themes_with_vocab:
        quote, praise_phrase = find_praise_quote(theme)
        if not quote:
            continue

        claim_matches = match_theme_to_claims(vocab, claims_with_vocab)
        coverage_ratio = marketing_coverage_ratio(vocab, claim_matches)
        if coverage_ratio >= HIDDEN_STRENGTH_COVERAGE_CEILING:
            continue

        closest_claim_ids = [claim_id for claim_id, _ in claim_matches]
        candidates.append({
            "theme_id": theme["theme_id"],
            "theme": theme["theme"],
            "sentiment": theme["sentiment"],
            "mention_count": theme["mention_count"],
            "evidence_review_ids": list(theme["example_review_ids"]),
            "evidence_quote": quote,
            "praise_signal": praise_phrase,
            "marketing_coverage_ratio": round(coverage_ratio, 2),
            "marketing_coverage": "none" if not closest_claim_ids else "minimal",
            "closest_marketing_claim_ids": closest_claim_ids,
            "rationale": (
                f"Players praise this ({praise_phrase!r} in a review quote) and it "
                f"comes up in {theme['mention_count']} reviews, but "
                + (
                    "no marketing claim shares its vocabulary."
                    if not closest_claim_ids
                    else f"only claim(s) {', '.join(closest_claim_ids)} touch it in passing "
                         f"({int(coverage_ratio * 100)}% vocabulary overlap)."
                )
            ),
        })

    candidates.sort(key=lambda c: c["mention_count"], reverse=True)
    return candidates[:limit]


def find_marketing_disconnects(claims, themes_with_vocab, limit=5):
    candidates = []

    for claim in claims:
        c_vocab = claim_vocab(claim)
        if len(c_vocab) < MIN_CLAIM_TOKENS:
            # Section headers like "EXPLORE" or "BUILD" aren't substantive
            # claims — skip so they can't crowd out real disconnects.
            continue

        theme_matches = match_claim_to_themes(c_vocab, themes_with_vocab)
        total_related_mentions = sum(m[1] for m in theme_matches)

        related_theme_ids = [m[0] for m in theme_matches]
        candidates.append({
            "claim_id": claim["claim_id"],
            "claim_text": claim["text"],
            "related_theme_ids": related_theme_ids,
            "total_related_mentions": total_related_mentions,
            "player_discussion": "none" if not related_theme_ids else "rare",
            "_specificity": len(c_vocab),
            "rationale": (
                "No player review theme shares this claim's vocabulary — it does "
                "not come up in player discussion at all."
                if not related_theme_ids
                else (
                    f"Only theme(s) {', '.join(related_theme_ids)} touch on this "
                    f"claim, totaling {total_related_mentions} review mentions — "
                    "rarely discussed, not absent."
                )
            ),
        })

    # Rank lowest player discussion first (zero-overlap claims, then lowest
    # mention totals). Among ties, prefer more specific/substantive claims
    # (more significant words) so the "most disconnected" and most concrete
    # claims surface at the top rather than an arbitrary tie order.
    candidates.sort(key=lambda c: (c["total_related_mentions"], -c["_specificity"]))
    top = candidates[:limit]
    for c in top:
        del c["_specificity"]
    return top


def validate_ids(gaps, themes, claims):
    """Guard against fabricated IDs: everything referenced must exist in source data."""
    theme_ids = {t["theme_id"] for t in themes}
    claim_ids = {c["claim_id"] for c in claims}
    review_ids = {rid for t in themes for rid in t["example_review_ids"]}

    for hs in gaps["hidden_strengths"]:
        assert hs["theme_id"] in theme_ids, f"unknown theme_id {hs['theme_id']}"
        for rid in hs["evidence_review_ids"]:
            assert rid in review_ids, f"unknown review_id {rid}"
        for cid in hs["closest_marketing_claim_ids"]:
            assert cid in claim_ids, f"unknown claim_id {cid}"

    for md in gaps["marketing_disconnects"]:
        assert md["claim_id"] in claim_ids, f"unknown claim_id {md['claim_id']}"
        for tid in md["related_theme_ids"]:
            assert tid in theme_ids, f"unknown theme_id {tid}"


def main():
    with THEMES_PATH.open() as f:
        themes_data = json.load(f)
    with MARKETING_PATH.open() as f:
        marketing_data = json.load(f)

    themes = themes_data["themes"]
    claims = marketing_data["claims"]

    claims_with_vocab = [(c, claim_vocab(c)) for c in claims]
    themes_with_vocab = [(t, theme_vocab(t)) for t in themes]

    hidden_strengths = find_hidden_strengths(themes, claims_with_vocab, limit=5)
    marketing_disconnects = find_marketing_disconnects(claims, themes_with_vocab, limit=5)

    gaps = {
        "hidden_strengths": hidden_strengths,
        "marketing_disconnects": marketing_disconnects,
    }

    validate_ids(gaps, themes, claims)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(gaps, f, indent=2)
        f.write("\n")

    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}\n")

    print(f"=== Top {len(hidden_strengths)} Hidden Strengths ===")
    for hs in hidden_strengths:
        print(f"- [{hs['theme_id']}] {hs['theme']} (mentions: {hs['mention_count']})")
        print(f"    quote: \"{hs['evidence_quote']}\"")
        print(f"    evidence review_ids: {hs['evidence_review_ids']}")
        print(f"    marketing coverage: {hs['marketing_coverage']} "
              f"{hs['closest_marketing_claim_ids']}")
        print()

    print(f"=== Top {len(marketing_disconnects)} Marketing Disconnects ===")
    for md in marketing_disconnects:
        print(f"- [{md['claim_id']}] {md['claim_text']}")
        print(f"    player discussion: {md['player_discussion']} "
              f"(related themes: {md['related_theme_ids']}, "
              f"total mentions: {md['total_related_mentions']})")
        print()


if __name__ == "__main__":
    main()
