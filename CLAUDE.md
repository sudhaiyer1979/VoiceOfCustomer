# CLAUDE.md

Guidance for Claude (or any agent) working in this repository.

## Project

Voice of Customer analyzes Steam game reviews against a game's marketing
claims to surface hidden strengths, marketing disconnects, and vocabulary
gaps between how players talk about a game and how it's marketed.

## Repository layout

```
scripts/    Pipeline scripts (see below) and scripts/validate_project.py
data/       JSON produced/consumed by the pipeline
output/     Generated artifacts (dashboard.html)
CLAUDE.md   This file
README.md   Human-facing project overview
```

## Pipeline

Each stage reads the previous stage's output and writes one JSON file to
`data/`, except the last stage which renders the dashboard to `output/`.

| Script | Output |
|---|---|
| `scripts/collect_reviews.py` | `data/reviews.json` |
| `scripts/collect_marketing.py` | `data/marketing.json` |
| `scripts/find_themes.py` | `data/review_themes.json` |
| `scripts/find_gaps.py` | `data/gaps.json` |
| `scripts/vocab_gap.py` | `data/vocabulary.json` |
| `scripts/build_dashboard.py` | `output/dashboard.html` |

Run `python scripts/validate_project.py` at any time to check which
pipeline scripts and data files exist, and whether existing JSON files
have the required fields below.

## Required data formats

### `data/reviews.json`

Top level:
- `game_name`
- `source_url`
- `app_id`
- `review_count`
- `reviews` — list of review objects

Each review object:
- `review_id`
- `text`
- `recommended`
- `date`

### `data/marketing.json`

Top level:
- `game_name`
- `source_url`
- `claims` — list of claim objects

Each claim object:
- `claim_id`
- `text`

### `data/review_themes.json`

Top level:
- `game_name`
- `themes` — list of theme objects

Each theme object:
- `theme_id`
- `theme`
- `sentiment`
- `mention_count`
- `keywords`
- `example_review_ids`
- `quotes`

### `data/gaps.json`

Top level:
- `hidden_strengths`
- `marketing_disconnects`

### `data/vocabulary.json`

Top level:
- `review_only_terms`
- `marketing_only_terms`
- `same_idea_different_words`

## Conventions

- Every script in `scripts/` reads its inputs from `data/` (or hits an
  external source for the two collection scripts) and writes exactly one
  file, per the pipeline table above.
- IDs (`review_id`, `claim_id`, `theme_id`) are stable strings referenced
  across files — e.g. `example_review_ids` in `review_themes.json` refers
  back to `review_id` values in `reviews.json`.
- Keep `scripts/validate_project.py` in sync if the expected file list or
  required fields change.
