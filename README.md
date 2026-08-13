# Voice of Customer

Analyzes Steam game reviews against a game's marketing claims to find:

- **Hidden strengths** — things players love that marketing doesn't mention
- **Marketing disconnects** — claims players don't back up, or push back on
- **Vocabulary gaps** — the same idea described in different words by players vs. marketing

## Layout

```
scripts/    Pipeline scripts + scripts/validate_project.py
data/       JSON produced/consumed by the pipeline
output/     Generated dashboard.html
CLAUDE.md   Data formats and conventions for working in this repo
```

## Pipeline

Run in order; each stage writes one file consumed by the next.

1. `scripts/collect_reviews.py` → `data/reviews.json`
2. `scripts/collect_marketing.py` → `data/marketing.json`
3. `scripts/find_themes.py` → `data/review_themes.json`
4. `scripts/find_gaps.py` → `data/gaps.json`
5. `scripts/vocab_gap.py` → `data/vocabulary.json`
6. `scripts/build_dashboard.py` → `output/dashboard.html`

See `CLAUDE.md` for the required JSON schema for each data file.

## Validating setup

```
python scripts/validate_project.py
```

Reports which pipeline scripts and data files exist yet, and whether any
existing JSON file is missing required fields. Exits non-zero only on a
structural problem (missing `scripts/`/`data/`/`output/` directories, or
a malformed/invalid existing file) — missing pipeline outputs that simply
haven't been generated yet are reported as warnings, not failures.
