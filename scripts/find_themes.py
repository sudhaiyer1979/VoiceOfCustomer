#!/usr/bin/env python3
"""Find recurring player themes in real reviews and write data/review_themes.json.

Usage:
    python scripts/find_themes.py
    python scripts/find_themes.py --min-themes 8 --max-themes 12 --show-uncovered

Reads data/reviews.json (produced by scripts/collect_reviews.py) and groups the
real review text into recurring player themes.

How it works:

1. Each candidate theme in THEME_LIBRARY is a plain-English topic plus the
   vocabulary players actually use for it (word-boundary patterns). A review
   "mentions" a theme when any of that theme's patterns matches its text, so
   `mention_count` is a count of real reviews, never an estimate.
2. Themes that too few reviews mention are dropped, and the strongest
   MAX_THEMES remain -- the library is deliberately larger than the number of
   themes kept so the same script can be re-run against another game's reviews
   and surface whichever topics that audience actually talks about.
3. `sentiment` compares a theme's recommend rate against the corpus baseline
   recommend rate, so a theme is only "positive" when it beats how this game's
   reviewers already vote overall.
4. `keywords` are mined from the matching reviews themselves (terms that are
   over-represented in the theme versus the whole corpus) with STOPWORDS --
   including generic terms like "game", "play", "player" and the game's own
   name -- filtered out so only meaningful vocabulary survives.
5. `quotes` are verbatim review text: whole sentences (or whole short reviews)
   copied out of data/reviews.json with runs of whitespace collapsed. No quote
   is ever paraphrased, truncated mid-sentence, or invented, and every quote is
   re-checked against its source review before the file is written.

Never fabricates data -- if data/reviews.json is missing or holds no usable
reviews, the script stops and reports the real error.
"""

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = ROOT / "data" / "reviews.json"
OUTPUT_PATH = ROOT / "data" / "review_themes.json"

MIN_THEMES = 8
MAX_THEMES = 12
MIN_MENTIONS = 10
QUOTES_PER_THEME = 3
KEYWORDS_PER_THEME = 8
MAX_QUOTE_CHARS = 300
MIN_QUOTE_CHARS = 40

# Sentiment bands, expressed as a theme's recommend rate minus the corpus
# baseline recommend rate. Reviews for a given game skew one way overall, so a
# theme only counts as positive/negative when it moves the needle off that
# baseline.
SENTIMENT_MARGIN = 0.07

# Words that carry no signal for this analysis: the game's own name, the
# vocabulary of reviewing itself, and ordinary English filler. Used when mining
# keywords out of the matching reviews.
STOPWORDS = {
    # explicitly excluded low-signal terms
    "game", "games", "gameplay", "play", "plays", "played", "playing",
    "player", "players", "rust", "rusty",
    # review boilerplate
    "recommend", "recommended", "review", "reviews", "steam", "buy", "bought",
    "worth", "overall", "opinion", "star", "stars", "pros", "cons",
    # generic English filler
    "the", "and", "you", "your", "youre", "yours", "this", "that", "then",
    "than", "there", "their", "theyre", "them", "they", "these", "those",
    "for", "but", "with", "have", "has", "had", "having", "not", "just",
    "its", "it's", "was", "were", "are", "been", "being", "can", "cant",
    "can't", "cannot", "will", "wont", "won't", "would", "wouldnt", "could",
    "should", "dont", "don't", "doesnt", "doesn't", "didnt", "didn't", "get",
    "gets", "getting", "got", "gotten", "make", "makes", "made", "making",
    "even", "ever", "every", "all", "any", "some", "much", "many", "more",
    "most", "less", "very", "really", "quite", "still", "also", "too", "one",
    "two", "out", "off", "into", "onto", "from", "when", "what", "who",
    "whom", "why", "how", "where", "which", "while", "about", "after",
    "before", "back", "over", "under", "again", "because", "like", "likes",
    "liked", "want", "wants", "wanted", "know", "knows", "knew", "think",
    "thought", "see", "saw", "seen", "look", "looks", "looking", "feel",
    "feels", "felt", "say", "says", "said", "way", "ways", "thing", "things",
    "stuff", "lot", "lots", "bit", "now", "here", "yes", "yeah", "nah",
    "good", "great", "nice", "bad", "best", "worst", "awesome", "amazing",
    "cool", "love", "loves", "loved", "hate", "hates", "hated", "fun",
    "funny", "put", "take", "takes", "took", "give", "gives", "gave", "come",
    "comes", "came", "went", "goes", "going", "does", "did", "doing", "own",
    "same", "other", "others", "another", "first", "last", "next", "own",
    "never", "always", "sometimes", "maybe", "probably", "definitely",
    "actually", "literally", "honestly", "basically", "pretty", "super",
    "little", "big", "long", "short", "new", "old", "need", "needs",
    "needed", "try", "tried", "trying", "use", "used", "using", "keep",
    "keeps", "kept", "let", "lets", "well", "sure", "okay", "must", "may",
    "might", "shall", "away", "around", "though", "although", "however",
    "anything", "everything", "nothing", "something", "someone", "anyone",
    "everyone", "nobody", "myself", "yourself", "itself", "himself",
    "herself", "themselves", "with", "without", "within", "yet", "per",
    "etc", "eeee", "aaaa",
    # pronouns and generic verbs that survive the filters above but say
    # nothing about what a theme is
    "him", "his", "her", "hers", "she", "hes", "she's", "he's", "himself",
    "our", "ours", "mine", "who's", "whos", "find", "finds", "finding",
    "start", "starts", "started", "starting", "help", "helps", "helped",
    "idea", "ideas", "plan", "plans", "end", "ends", "ended",
}

# Sentences containing any of these are skipped when picking quotes: Steam's
# own profanity censoring (which renders as hearts) and slurs, neither of which
# belongs in a customer-facing dashboard. The underlying review still counts
# toward mention_count -- only its use as a pull quote is skipped.
QUOTE_BLOCKLIST = re.compile(
    r"♥|\bn[- ]?words?\b|\bnigg|\bfag|\bretard|\btrann|\bkys\b|\bkms\b|\bslurs?\b",
    re.IGNORECASE,
)

WORD_RE = re.compile(r"[a-z][a-z']+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Steam reviews can be written in markdown. A fragment carrying list bullets or
# heading marks reads as broken text once pulled out of its review, so it is
# skipped as a quote (the review still counts toward mention_count).
MARKDOWN_NOISE_RE = re.compile(r"\*\*|^\s*[*#-]\s|\s[*#]\s|\bhttps?://")

# Candidate themes: (theme name, [player vocabulary patterns]).
#
# Patterns are matched case-insensitively against the review text. Keep them
# specific -- a pattern that fires on ordinary filler will inflate a theme's
# mention_count with reviews that are not really about it.
THEME_LIBRARY = [
    (
        "Time sink that takes over your life",
        [
            r"\d+\s*(?:,\d{3})*\+?\s*(?:hours|hrs)\b", r"\bhours?\b", r"\bhrs\b",
            r"\baddict\w*\b", r"\bno life\b", r"\bnolife\w*\b", r"\bsocial life\b",
            r"\blost my life\b", r"\bruin\w* my life\b", r"\blife (?:is )?(?:over|gone)\b",
            r"\bunemploy\w*\b", r"\bfull.?time job\b", r"\bsecond job\b",
            r"\bmore than a job\b", r"\bsleep\w*\b", r"\btime consuming\b",
            r"\bcan'?t stop\b", r"\bcant stop\b", r"\bevery day\b", r"\beveryday\b",
            r"\bwaste of time\b", r"\bfree time\b",
        ],
    ),
    (
        "Toxic community and verbal abuse",
        [
            r"\btoxic\w*\b", r"\bracis\w*\b", r"\bslurs?\b", r"\bsquea\w*\b",
            r"\bscream\w*\b", r"\byell\w*\b", r"\binsult\w*\b", r"\brude\b",
            r"\bharass\w*\b", r"\btrash talk\w*\b", r"\bcalled me\b",
            r"\bnasty\b", r"\bbully\w*\b", r"\bvoice chat\b", r"\bswear\w*\b",
            # "kid" on its own is the corpus's fresh-spawn loot meme ("found an
            # AK before food, felt like a kid in Iraq"), not toxicity -- only
            # count it where the review is clearly describing another player.
            r"\b(?:annoying|nasty|screaming|squeaky|toxic|little|random) kids?\b",
            r"\bkids? (?:in your ears|screaming|yelling|with a mic)\b",
        ],
    ),
    (
        "Constant PvP death and fresh-spawn kills",
        [
            r"\bkill(?:ed|s|ing)?\b", r"\bmurder\w*\b", r"\bdie\b", r"\bdying\b",
            r"\bdied\b", r"\bdeath\w*\b", r"\bshot\b", r"\bshoot\w*\b",
            r"\bpvp\b", r"\bnaked\w*\b", r"\bbeach\b", r"\bspawn\w*\b",
            r"\beoka\b", r"\bak\b", r"\bgun\w*\b", r"\brock\b", r"\bbow\b",
            r"\bsnipe\w*\b", r"\bcamp(?:ed|ing|er|ers)\b",
        ],
    ),
    (
        "Getting raided and losing everything",
        [
            r"\braid(?:ed|s|ing|er|ers)?\b", r"\boffline\w*\b", r"\bgrief\w*\b",
            r"\blose (?:it |them |your |my |all )?\w*\s?all\b",
            r"\blost (?:it |them |your |my |all )?\w*\s?all\b",
            r"\blose everything\b", r"\blost everything\b", r"\bstole\w*\b",
            r"\brob(?:bed|bing)\b", r"\bloot\w*\b", r"\bdoor camp\w*\b",
            r"\bc4\b", r"\brocket\w*\b", r"\bexplos\w*\b", r"\bboom\w*\b",
        ],
    ),
    (
        "Base building and engineering",
        [
            r"\bbuild(?:s|ing|er|ers)?\b", r"\bbuilt\b", r"\bbase(?:s)?\b",
            r"\bbunker\w*\b", r"\bhoneycomb\w*\b", r"\b\d+x\d+\b",
            r"\belectric\w*\b", r"\bturret\w*\b", r"\bfurnace\w*\b",
            r"\bsorting machine\b", r"\bdesign\w*\b", r"\bwall(?:s)?\b",
            r"\bdoor(?:s)?\b", r"\bhouse(?:s)?\b", r"\bcraft\w*\b",
        ],
    ),
    (
        "Brutal grind and slow progression",
        [
            r"\bgrind\w*\b", r"\bgrindy\b", r"\bfarm\w*\b", r"\bscrap\b",
            r"\bblueprint\w*\b", r"\bsulfur\b", r"\bnodes?\b", r"\bmining\b",
            r"\bprogress\w*\b", r"\btedious\b", r"\bstart(?:ing)? over\b",
            r"\bstart(?:ing)? from scratch\b", r"\bmonoton\w*\b", r"\bgather\w*\b",
        ],
    ),
    (
        # Players talk about cheating and the anti-cheat that polices it as one
        # grievance -- being shot by a hacker and being wrongly banned are both
        # "the anti-cheat is not working" -- so they are scored as one theme.
        "Cheaters, bans and anti-cheat",
        [
            r"\bcheat(?:s|er|ers|ing)\b", r"\bhack(?:s|er|ers|ing|ed)\b",
            r"\baimbot\w*\b", r"\bwall ?hack\w*\b", r"\besp\b", r"\bscript(?:s|er|ers)\b",
            r"\bexploit\w*\b", r"\bmacro\w*\b", r"\bban(?:s|ned|ning)\b",
            r"\bunban\w*\b", r"\beac\b", r"\beasy anti.?cheat\b", r"\banti.?cheat\b",
            r"\bappeal\w*\b", r"\bfalse (?:ban|flag)\w*\b", r"\bvac\b",
        ],
    ),
    (
        "Performance, crashes and optimization",
        [
            r"\blag(?:s|gy|ging)?\b", r"\bfps\b", r"\bframe ?rate\w*\b",
            r"\bcrash\w*\b", r"\boptimi\w*\b", r"\bstutter\w*\b", r"\bfreez\w*\b",
            r"\bload(?:ing)? (?:in|into|screen|time)\w*\b", r"\blow end\b",
            r"\bruns? (?:well|smooth\w*|badly|like)\b", r"\bperformance\b",
            r"\bglitch\w*\b", r"\bbug(?:s|gy|ged)?\b", r"\bram\b", r"\bgpu\b",
            # Bare "pc" is usually incidental ("switched from console to pc"),
            # so only match hardware talk that is actually about running it.
            r"\b(?:low|high|bad|good|decent|potato) ?(?:end|grade)? ?pc\b",
            r"\brun (?:this|the game|rust|it)\b", r"\bgraphics\b", r"\bsettings\b",
            r"\bvideo cards?\b", r"\bwont (?:start|launch|open)\b",
        ],
    ),
    (
        "Solo players versus groups and zergs",
        [
            r"\bsolo\w*\b", r"\bzerg\w*\b", r"\bclan\w*\b", r"\bgroup(?:s|ed)?\b",
            r"\bteam(?:s|ed|mate|mates)?\b", r"\b\d+\s*man\b", r"\bduo\w*\b",
            r"\btrio\w*\b", r"\bsquad\w*\b", r"\balone\b", r"\bby yourself\b",
            r"\bby myself\b",
        ],
    ),
    (
        "Harsh new-player learning curve",
        [
            r"\bnew players?\b", r"\bnewer players?\b", r"\bbeginner\w*\b",
            r"\bnoob\w*\b", r"\blearn\w*\b", r"\btutorial\w*\b",
            r"\bsteep\b", r"\blearning curve\b", r"\bunforgiving\b",
            r"\bhard to (?:get into|start|learn)\b", r"\bfirst time\b",
            r"\bstarted? playing\b", r"\bconfus\w*\b", r"\bno idea\b",
            r"\bexperienced? players?\b", r"\bveteran\w*\b",
        ],
    ),
    (
        "Playing with friends and rare friendliness",
        [
            r"\bfriends?\b", r"\bfriendly\b", r"\bfriendship\w*\b", r"\bchill\w*\b",
            r"\bcommunity\b", r"\bteammates?\b", r"\bally\b", r"\ballies\b",
            r"\bally(?:ing)?\b", r"\bwith (?:a|my|your|the) (?:buddy|buddies|mate|mates)\b",
            r"\bmet (?:a|some|this)\b", r"\btrust\w*\b", r"\bwholesome\b",
        ],
    ),
    (
        "Wipe cycle and starting from scratch",
        [
            r"\bwipe(?:s|d)?\b", r"\bwipe ?day\b", r"\bforce ?wipe\b",
            r"\bmonthly\b", r"\bweekly\b", r"\breset(?:s|ting)?\b",
            r"\bfresh start\w*\b", r"\ball over again\b", r"\bstart(?:s|ing)? again\b",
        ],
    ),
    (
        "Choosing a server and dealing with admins",
        [
            r"\bserver(?:s)?\b", r"\bpop(?:ulation)?\b", r"\bvanilla\b",
            r"\bmodded\b", r"\b\d+x\b", r"\bofficial\b", r"\bcommunity server\w*\b",
            r"\badmin(?:s)?\b", r"\bqueue\w*\b", r"\bjoin(?:ed|ing)? a\b",
        ],
    ),
    (
        "Survival, hunger and the environment",
        [
            r"\bsurviv\w*\b", r"\bfood\b", r"\bhunger\b", r"\bhungry\b",
            r"\bstarv\w*\b", r"\bwater\b", r"\bthirst\w*\b", r"\bbears?\b",
            r"\bwolf\b", r"\bwolves\b", r"\bwildlife\b", r"\banimals?\b",
            r"\bcold\b", r"\bnight\b", r"\bhunt\w*\b", r"\bradiation\b", r"\brad\b",
        ],
    ),
    (
        "Updates and developer support",
        [
            r"\bupdate(?:s|d)?\b", r"\bfacepunch\b", r"\bdevs?\b",
            r"\bdeveloper(?:s)?\b", r"\bpatch(?:es|ed)?\b", r"\bdlc\b",
            r"\bsupport\b", r"\bfix(?:es|ed|ing)?\b", r"\bmicrotransaction\w*\b",
            # "skin" alone is body/character skin in this corpus; only the
            # monetization sense belongs to the developer theme.
            r"\b(?:money from|selling|buy) skins\b", r"\bskin (?:prices?|market)\b",
        ],
    ),
    (
        "Rage, stress and emotional toll",
        [
            r"\brage\w*\b", r"\bangry\b", r"\banger\b", r"\bstress\w*\b",
            r"\bfrustrat\w*\b", r"\bpain\w*\b", r"\btortur\w*\b", r"\bsuffer\w*\b",
            r"\bmiser\w*\b", r"\bdepress\w*\b", r"\bcry\w*\b", r"\bcried\b",
            r"\btilt\w*\b", r"\bmental\w*\b", r"\bagoniz\w*\b", r"\baggravat\w*\b",
        ],
    ),
]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_reviews(path):
    """Read reviews.json and return (game_name, source_url, reviews)."""
    if not path.is_file():
        raise RuntimeError(
            f"{path} not found. Run scripts/collect_reviews.py first."
        )

    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{path} is not valid JSON: {e}") from e

    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        raise RuntimeError(f"{path} contains no reviews to analyze.")

    usable = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        text = (review.get("text") or "").strip()
        review_id = review.get("review_id")
        if not text or review_id is None:
            continue
        usable.append(
            {
                "review_id": str(review_id),
                "text": text,
                "normalized": collapse_whitespace(text),
                "recommended": bool(review.get("recommended")),
            }
        )

    if not usable:
        raise RuntimeError(f"{path} contains no reviews with usable text.")

    return payload.get("game_name") or "Unknown", payload.get("source_url", ""), usable


def collapse_whitespace(text):
    """Collapse runs of whitespace without changing any of the words."""
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Theme matching
# --------------------------------------------------------------------------

def compile_library(library):
    return [
        (name, [re.compile(pattern, re.IGNORECASE) for pattern in patterns])
        for name, patterns in library
    ]


def match_theme(review, patterns):
    """Return the list of distinct phrases in this review that hit the theme."""
    hits = []
    for pattern in patterns:
        for found in pattern.findall(review["normalized"]):
            phrase = found if isinstance(found, str) else found[0]
            if phrase:
                hits.append(phrase.lower())
    return hits


def tokenize(text):
    """Lowercase word tokens with accents folded away, stopwords removed."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return [w for w in WORD_RE.findall(folded) if w not in STOPWORDS and len(w) > 2]


def mine_keywords(matched, corpus_doc_freq, corpus_size, limit):
    """Pick terms that are over-represented in a theme's reviews.

    Scored by how much more often a term shows up in the theme's reviews than
    in the corpus as a whole, weighted by how many theme reviews use it, so a
    keyword has to be both distinctive and common to survive.
    """
    theme_doc_freq = Counter()
    for review in matched:
        theme_doc_freq.update(set(tokenize(review["text"])))

    min_docs = max(3, int(0.02 * len(matched)))
    scored = []
    for term, count in theme_doc_freq.items():
        if count < min_docs:
            continue
        theme_rate = count / len(matched)
        corpus_rate = corpus_doc_freq.get(term, 0) / corpus_size
        if corpus_rate <= 0:
            continue
        lift = theme_rate / corpus_rate
        if lift <= 1.0:
            continue
        scored.append((lift * math.log1p(count), term))

    scored.sort(reverse=True)
    return [term for _, term in scored[:limit]]


def classify_sentiment(matched, baseline_rate):
    """Positive/negative/mixed, relative to how this corpus votes overall."""
    if not matched:
        return "mixed"
    rate = sum(1 for r in matched if r["recommended"]) / len(matched)
    if rate >= baseline_rate + SENTIMENT_MARGIN:
        return "positive"
    if rate <= baseline_rate - SENTIMENT_MARGIN:
        return "negative"
    return "mixed"


# --------------------------------------------------------------------------
# Quotes (verbatim, always traceable to a real review)
# --------------------------------------------------------------------------

def is_quotable(sentence):
    """Readable, dashboard-safe, and long enough to say something."""
    if not MIN_QUOTE_CHARS <= len(sentence) <= MAX_QUOTE_CHARS:
        return False
    if QUOTE_BLOCKLIST.search(sentence):
        return False
    if MARKDOWN_NOISE_RE.search(sentence):
        return False
    letters = [c for c in sentence if c.isalpha()]
    if len(letters) < 0.5 * len(sentence):
        return False
    # Skip reviews written in another language / heavy emoji spam: quotes are
    # only useful downstream if an English-reading stakeholder can read them.
    ascii_letters = [c for c in letters if c.isascii()]
    if len(ascii_letters) < 0.98 * len(letters):
        return False
    return True


def candidate_quotes(review, patterns):
    """Verbatim quote candidates from one review, longest-context first.

    A candidate is either the whole (whitespace-collapsed) review or one whole
    sentence of it -- both are exact substrings of the real review text, so
    nothing is ever paraphrased or cut off mid-thought.
    """
    candidates = []
    whole = review["normalized"]
    if is_quotable(whole):
        candidates.append(whole)

    for sentence in SENTENCE_SPLIT_RE.split(whole):
        sentence = collapse_whitespace(sentence)
        if sentence and sentence != whole and is_quotable(sentence):
            candidates.append(sentence)

    scored = []
    for candidate in candidates:
        hits = sum(1 for p in patterns if p.search(candidate))
        if hits:
            # Prefer quotes that speak to the theme, then compact ones.
            scored.append((-hits, len(candidate), candidate))
    scored.sort()
    return [c for _, _, c in scored]


def pick_quotes(matched, patterns, limit, already_quoted):
    """Up to `limit` verbatim quotes, each from a different review.

    A handful of long, keyword-dense reviews would otherwise supply the quotes
    for every theme, so reviews already quoted elsewhere sort last: the themes
    end up evidenced by many different players rather than the same few.
    """
    ordered = sorted(
        matched,
        key=lambda r: (
            r["review_id"] in already_quoted,
            -len(match_theme(r, patterns)),
            len(r["normalized"]),
        ),
    )

    quotes = []
    seen_ids = []
    for review in ordered:
        if len(quotes) >= limit:
            break
        for candidate in candidate_quotes(review, patterns):
            if candidate not in quotes:
                quotes.append(candidate)
                seen_ids.append(review["review_id"])
                break
    return quotes, seen_ids


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def analyze(reviews, library, min_mentions, max_themes, quotes_per_theme,
            keywords_per_theme):
    corpus_doc_freq = Counter()
    for review in reviews:
        corpus_doc_freq.update(set(tokenize(review["text"])))
    corpus_size = len(reviews)
    baseline_rate = sum(1 for r in reviews if r["recommended"]) / corpus_size

    found = []
    already_quoted = set()
    for name, patterns in compile_library(library):
        matched = [r for r in reviews if match_theme(r, patterns)]
        if len(matched) < min_mentions:
            continue

        quotes, quote_ids = pick_quotes(
            matched, patterns, quotes_per_theme, already_quoted
        )
        already_quoted.update(quote_ids)

        # example_review_ids always covers the quoted reviews first, so every
        # quote stays traceable to an ID listed on the same theme.
        example_ids = list(quote_ids)
        for review in matched:
            if len(example_ids) >= max(5, len(quote_ids)):
                break
            if review["review_id"] not in example_ids:
                example_ids.append(review["review_id"])

        found.append(
            {
                "theme": name,
                "sentiment": classify_sentiment(matched, baseline_rate),
                "mention_count": len(matched),
                "keywords": mine_keywords(
                    matched, corpus_doc_freq, corpus_size, keywords_per_theme
                ),
                "example_review_ids": example_ids,
                "quotes": quotes,
            }
        )

    found.sort(key=lambda t: t["mention_count"], reverse=True)
    found = found[:max_themes]

    for i, theme in enumerate(found, start=1):
        theme["theme_id"] = f"T{i:03d}"

    # Emit the fields in the order CLAUDE.md documents them.
    return [
        {
            "theme_id": t["theme_id"],
            "theme": t["theme"],
            "sentiment": t["sentiment"],
            "mention_count": t["mention_count"],
            "keywords": t["keywords"],
            "example_review_ids": t["example_review_ids"],
            "quotes": t["quotes"],
        }
        for t in found
    ], baseline_rate


def verify(themes, reviews):
    """Fail loudly if any ID or quote can't be traced back to a real review."""
    by_id = {r["review_id"]: r for r in reviews}
    errors = []

    for theme in themes:
        for review_id in theme["example_review_ids"]:
            if review_id not in by_id:
                errors.append(
                    f"{theme['theme_id']}: review_id {review_id} is not in reviews.json"
                )
        for quote in theme["quotes"]:
            if not any(quote in r["normalized"] for r in reviews):
                errors.append(
                    f"{theme['theme_id']}: quote is not verbatim review text: {quote[:60]!r}"
                )

    return errors


def uncovered_terms(reviews, library, limit=40):
    """Frequent vocabulary no theme in the library covers yet.

    Purely a maintenance aid for pointing the same script at another game:
    anything big showing up here is a theme worth adding to THEME_LIBRARY.
    """
    compiled = compile_library(library)
    covered = Counter()
    doc_freq = Counter()
    for review in reviews:
        terms = set(tokenize(review["text"]))
        doc_freq.update(terms)
        for _, patterns in compiled:
            if match_theme(review, patterns):
                covered.update(terms)

    remaining = Counter(
        {term: count for term, count in doc_freq.items() if covered[term] < count * 0.5}
    )
    return remaining.most_common(limit)


def main():
    parser = argparse.ArgumentParser(
        description="Find recurring player themes in real reviews."
    )
    parser.add_argument("--reviews", type=Path, default=INPUT_PATH,
                        help="Path to reviews.json (default: data/reviews.json)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH,
                        help="Where to write themes (default: data/review_themes.json)")
    parser.add_argument("--min-themes", type=int, default=MIN_THEMES,
                        help=f"Fail if fewer themes are found (default: {MIN_THEMES})")
    parser.add_argument("--max-themes", type=int, default=MAX_THEMES,
                        help=f"Keep at most this many themes (default: {MAX_THEMES})")
    parser.add_argument("--min-mentions", type=int, default=MIN_MENTIONS,
                        help=f"Drop themes below this many reviews (default: {MIN_MENTIONS})")
    parser.add_argument("--quotes", type=int, default=QUOTES_PER_THEME,
                        help=f"Quotes per theme (default: {QUOTES_PER_THEME})")
    parser.add_argument("--keywords", type=int, default=KEYWORDS_PER_THEME,
                        help=f"Keywords per theme (default: {KEYWORDS_PER_THEME})")
    parser.add_argument("--show-uncovered", action="store_true",
                        help="List frequent terms no theme covers (lexicon maintenance)")
    args = parser.parse_args()

    try:
        game_name, source_url, reviews = load_reviews(args.reviews)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    themes, baseline_rate = analyze(
        reviews,
        THEME_LIBRARY,
        args.min_mentions,
        args.max_themes,
        args.quotes,
        args.keywords,
    )

    if len(themes) < args.min_themes:
        print(
            f"ERROR: only {len(themes)} theme(s) cleared {args.min_mentions} mentions; "
            f"expected at least {args.min_themes}. Refusing to write a thin file.",
            file=sys.stderr,
        )
        sys.exit(1)

    errors = verify(themes, reviews)
    if errors:
        print("ERROR: traceability check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    output = {
        "game_name": game_name,
        "source_url": source_url,
        "review_count": len(reviews),
        "themes": themes,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Analyzed {len(reviews)} real reviews for '{game_name}'")
    print(f"Baseline recommend rate: {baseline_rate:.0%} (sentiment is relative to this)")
    print(f"Found {len(themes)} themes:\n")
    print(f"  {'ID':<6}{'MENTIONS':>9}  {'SENTIMENT':<10}THEME")
    for theme in themes:
        print(
            f"  {theme['theme_id']:<6}{theme['mention_count']:>9}  "
            f"{theme['sentiment']:<10}{theme['theme']}"
        )

    if args.show_uncovered:
        print("\nFrequent terms not covered by any theme:")
        for term, count in uncovered_terms(reviews, THEME_LIBRARY):
            print(f"  {count:>5}  {term}")

    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
