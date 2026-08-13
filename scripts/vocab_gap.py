#!/usr/bin/env python3
"""Voice of Customer - WS6: Language Gap.

Compares the vocabulary players use in Steam reviews against the vocabulary a
game's marketing uses in its store claims, and surfaces:

  1. review_only_terms       - words / short phrases players use often but
                               marketing (almost) never uses.
  2. marketing_only_terms    - words / short phrases marketing uses but
                               players (almost) never use.
  3. same_idea_different_words - concepts where players and marketing describe
                               the same idea with different wording.

Inputs  (read from data/, per CLAUDE.md):
    data/reviews.json      - player reviews
    data/marketing.json    - marketing claims

Output  (exactly one file, per CLAUDE.md):
    data/vocabulary.json

Grounding guarantees (never invent wording):
  * Every player term / phrase comes verbatim from at least one real review,
    and the referenced review_ids exist in reviews.json.
  * Every marketing term / phrase comes verbatim from at least one real claim,
    and the referenced claim_ids exist in marketing.json.

The script is reusable: paths and thresholds are configurable via CLI flags.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

# --------------------------------------------------------------------------- #
# Vocabulary filtering
# --------------------------------------------------------------------------- #

# Words the task explicitly asks us to ignore, plus their obvious inflections.
IGNORE_WORDS = {
    "game", "games", "gaming",
    "play", "plays", "playing", "played",
    "player", "players",
    "rust",
}

# Common English function words that carry no "voice" signal.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "so", "as",
    "of", "at", "by", "for", "in", "into", "on", "onto", "to", "from", "with",
    "without", "about", "above", "below", "over", "under", "up", "down", "out",
    "off", "again", "further", "once", "here", "there", "when", "where", "why",
    "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "than", "too", "very",
    "can", "will", "just", "should", "now", "i", "me", "my", "myself", "we",
    "our", "ours", "you", "your", "yours", "he", "him", "his", "she", "her",
    "it", "its", "they", "them", "their", "theirs", "what", "which", "who",
    "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "having", "do", "does", "did",
    "doing", "would", "could", "should", "ought", "im", "ive", "id", "youre",
    "dont", "doesnt", "didnt", "cant", "couldnt", "wont", "wouldnt", "isnt",
    "arent", "wasnt", "werent", "aint", "theyre", "its", "thats", "theres",
    "get", "got", "getting", "go", "going", "goes", "went", "gone", "one",
    "two", "also", "even", "still", "yet", "ever", "never", "much", "many",
    "lot", "lots", "make", "makes", "made", "way", "thing", "things", "really",
    "actually", "maybe", "probably", "want", "wanted", "need", "needs", "let",
    "us", "him", "her", "s", "t", "re", "ve", "ll", "d", "m",
}

DROP = IGNORE_WORDS | STOPWORDS

TOKEN_RE = re.compile(r"[a-z][a-z']+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens (apostrophes kept, e.g. don't)."""
    return TOKEN_RE.findall(text.lower())


def content_ngrams(text: str, max_n: int = 3) -> set[str]:
    """Return the set of 'content' unigrams..max_n-grams in *text*.

    A term is kept only if none of its tokens is a stopword or an ignored
    word, so phrases like "real life" survive but "of the" or "the game" do
    not. Using a set gives document-frequency counting downstream.
    """
    toks = tokenize(text)
    terms: set[str] = set()
    for n in range(1, max_n + 1):
        for i in range(len(toks) - n + 1):
            gram = toks[i:i + n]
            if any(w in DROP for w in gram):
                continue
            if n == 1 and len(gram[0]) < 3:
                continue
            terms.add(" ".join(gram))
    return terms


# --------------------------------------------------------------------------- #
# Same-idea concept map
# --------------------------------------------------------------------------- #
#
# Each concept lists candidate *verbatim* marketing phrases and candidate
# *verbatim* player phrases. The script keeps a concept only if at least one
# marketing candidate literally appears in a real claim AND at least one
# player candidate literally appears in a real review. The wording is never
# invented - candidates are grounded against the corpora at run time, and the
# real claim_ids / review_ids are attached.

CONCEPTS = [
    {
        "concept": "Getting your base raided",
        "marketing": ["raiding their bases"],
        "player": ["raided", "got raided", "base raided"],
    },
    {
        "concept": "Hostile / abusive community",
        "marketing": ["other survivors", "prey on them"],
        "player": ["toxic", "toxic community"],
    },
    {
        "concept": "Player-versus-player combat",
        "marketing": ["prey on them", "raiding their bases"],
        "player": ["pvp", "pvp is"],
    },
    {
        "concept": "Effort spent earning progress",
        "marketing": ["hard-won goods", "hard-won"],
        "player": ["grind", "grinding", "the grind"],
    },
    {
        "concept": "Compulsive, can't-stop engagement",
        "marketing": ["last another night", "do whatever it takes"],
        "player": ["addicting", "addictive", "addicted", "addiction"],
    },
    {
        "concept": "Being killed by others",
        "marketing": ["be eaten", "prey on them"],
        "player": ["killed", "killed me", "get killed"],
    },
    {
        "concept": "Losing everything on a server reset",
        "marketing": ["last another night"],
        "player": ["wipe", "wiped", "after wipe"],
    },
    {
        "concept": "Starting out defenceless",
        "marketing": ["armed only with a rock", "naked"],
        "player": ["spawn", "fresh spawn", "naked"],
    },
]


# --------------------------------------------------------------------------- #
# Core analysis
# --------------------------------------------------------------------------- #

def build_index(records: list[dict], id_key: str, text_key: str,
                max_n: int) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Map each content term -> set of record-ids that contain it.

    Also return {record_id: lowercased_text} for verbatim substring lookups.
    """
    term_to_ids: dict[str, set[str]] = defaultdict(set)
    lowered: dict[str, str] = {}
    for rec in records:
        rid = rec[id_key]
        text = rec.get(text_key, "") or ""
        lowered[rid] = text.lower()
        for term in content_ngrams(text, max_n):
            term_to_ids[term].add(rid)
    return term_to_ids, lowered


def ids_containing(phrase: str, lowered: dict[str, str]) -> list[str]:
    """Real record-ids whose text literally contains *phrase* (verbatim)."""
    p = phrase.lower()
    return [rid for rid, text in lowered.items() if p in text]


def find_review_only(review_index, marketing_index, min_reviews, top,
                     review_order):
    """Terms frequent in reviews but absent from marketing."""
    order = {rid: i for i, rid in enumerate(review_order)}
    out = []
    for term, rids in review_index.items():
        if len(rids) < min_reviews:
            continue
        if term in marketing_index:  # appears in marketing -> not review-only
            continue
        examples = sorted(rids, key=lambda r: order.get(r, 1 << 30))[:5]
        out.append({
            "term": term,
            "review_count": len(rids),
            "example_review_ids": examples,
        })
    # More mentions first; break ties by shorter (more prominent) phrases then
    # alphabetically for stable output.
    out.sort(key=lambda d: (-d["review_count"], len(d["term"]), d["term"]))
    return out[:top]


def find_marketing_only(review_index, marketing_index, top):
    """Terms used by marketing but absent from reviews."""
    out = []
    for term, cids in marketing_index.items():
        if term in review_index:  # players use it too -> not marketing-only
            continue
        out.append({
            "term": term,
            "marketing_count": len(cids),
            "claim_ids": sorted(cids),
        })
    out.sort(key=lambda d: (-d["marketing_count"], len(d["term"]), d["term"]))
    return out[:top]


def find_same_idea(review_lower, marketing_lower, sample_reviews):
    """Concepts described with different wording on each side (grounded)."""
    out = []
    for spec in CONCEPTS:
        m_phrase = m_ids = p_phrase = p_ids = None
        for cand in spec["marketing"]:
            hits = ids_containing(cand, marketing_lower)
            if hits:
                m_phrase, m_ids = cand, sorted(hits)
                break
        for cand in spec["player"]:
            hits = ids_containing(cand, review_lower)
            if hits:
                p_phrase, p_ids = cand, hits
                break
        if not (m_phrase and p_phrase):
            continue  # one side has no real occurrence -> skip, never invent
        if m_phrase.lower() == p_phrase.lower():
            continue  # identical wording is not a language *gap*
        out.append({
            "concept": spec["concept"],
            "marketing_phrase": m_phrase,
            "player_phrase": p_phrase,
            "claim_ids": m_ids,
            "review_ids": sorted(p_ids)[:sample_reviews],
            "player_review_count": len(p_ids),
        })
    return out


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #

def verify(result: dict, review_ids: set[str], claim_ids: set[str]) -> None:
    """Assert every referenced id exists; raise on any dangling reference."""
    def check_reviews(ids, where):
        for rid in ids:
            if rid not in review_ids:
                raise ValueError(f"{where}: unknown review_id {rid!r}")

    def check_claims(ids, where):
        for cid in ids:
            if cid not in claim_ids:
                raise ValueError(f"{where}: unknown claim_id {cid!r}")

    for e in result["review_only_terms"]:
        check_reviews(e["example_review_ids"], f"review_only_terms[{e['term']!r}]")
    for e in result["marketing_only_terms"]:
        check_claims(e["claim_ids"], f"marketing_only_terms[{e['term']!r}]")
    for e in result["same_idea_different_words"]:
        check_claims(e["claim_ids"], f"same_idea[{e['concept']!r}]")
        check_reviews(e["review_ids"], f"same_idea[{e['concept']!r}]")


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def run(reviews_path: Path, marketing_path: Path, out_path: Path,
        max_n: int, min_reviews: int, top: int, sample_reviews: int) -> dict:
    reviews_doc = json.loads(reviews_path.read_text(encoding="utf-8"))
    marketing_doc = json.loads(marketing_path.read_text(encoding="utf-8"))

    reviews = reviews_doc["reviews"]
    claims = marketing_doc["claims"]
    review_order = [r["review_id"] for r in reviews]

    review_index, review_lower = build_index(reviews, "review_id", "text", max_n)
    marketing_index, marketing_lower = build_index(claims, "claim_id", "text", max_n)

    result = {
        "game_name": reviews_doc.get("game_name"),
        "review_only_terms": find_review_only(
            review_index, marketing_index, min_reviews, top, review_order),
        "marketing_only_terms": find_marketing_only(
            review_index, marketing_index, top),
        "same_idea_different_words": find_same_idea(
            review_lower, marketing_lower, sample_reviews),
    }

    verify(result,
           review_ids={r["review_id"] for r in reviews},
           claim_ids={c["claim_id"] for c in claims})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="WS6 - Language Gap analysis.")
    p.add_argument("--reviews", type=Path, default=root / "data" / "reviews.json")
    p.add_argument("--marketing", type=Path, default=root / "data" / "marketing.json")
    p.add_argument("--out", type=Path, default=root / "data" / "vocabulary.json")
    p.add_argument("--max-n", type=int, default=3,
                   help="Longest phrase length (in words) to consider.")
    p.add_argument("--min-reviews", type=int, default=3,
                   help="Min reviews a term must appear in to be review-only.")
    p.add_argument("--top", type=int, default=25,
                   help="Max terms to keep per list.")
    p.add_argument("--sample-reviews", type=int, default=10,
                   help="Max review_ids stored per same-idea concept.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = run(args.reviews, args.marketing, args.out,
                 args.max_n, args.min_reviews, args.top, args.sample_reviews)

    def show(title, rows, fmt):
        print(f"\n=== {title} ===")
        if not rows:
            print("  (none)")
        for i, row in enumerate(rows, 1):
            print(f"  {i:2}. {fmt(row)}")

    show("Top 10 player-only terms", result["review_only_terms"][:10],
         lambda r: f"{r['term']!r:24} ({r['review_count']} reviews)  "
                   f"e.g. {', '.join(r['example_review_ids'][:3])}")
    show("Top 10 marketing-only terms", result["marketing_only_terms"][:10],
         lambda r: f"{r['term']!r:24} ({r['marketing_count']} claims)  "
                   f"{', '.join(r['claim_ids'])}")
    show("Same idea, different words", result["same_idea_different_words"],
         lambda r: f"{r['concept']}\n        marketing: {r['marketing_phrase']!r} "
                   f"({', '.join(r['claim_ids'])})\n        players:   "
                   f"{r['player_phrase']!r} ({r['player_review_count']} reviews, "
                   f"e.g. {', '.join(r['review_ids'][:3])})")

    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
