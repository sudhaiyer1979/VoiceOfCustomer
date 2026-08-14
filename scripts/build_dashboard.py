#!/usr/bin/env python3
"""Render the Voice of Customer dashboard.

Reads the five pipeline JSON files from data/ and writes a single,
fully self-contained HTML file to output/dashboard.html. The output
has no external dependencies (no JS/CSS/font/image URLs, no server,
no internet access) -- it can be double-clicked and opened directly
in a browser.
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output" / "dashboard.html"


def load(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return json.load(f)


def esc(text):
    return html.escape(str(text), quote=True)


def build_reviews_index(reviews):
    return {r["review_id"]: r for r in reviews}


def summary_section(reviews_data, marketing_data, themes_data):
    review_count = reviews_data.get("review_count", len(reviews_data.get("reviews", [])))
    claim_count = len(marketing_data.get("claims", []))
    theme_count = len(themes_data.get("themes", []))
    return f"""
    <section class="summary">
      <div class="stat-grid">
        <div class="stat-tile">
          <div class="stat-number">{review_count:,}</div>
          <div class="stat-label">Player Reviews Analyzed</div>
        </div>
        <div class="stat-tile">
          <div class="stat-number">{claim_count}</div>
          <div class="stat-label">Marketing Claims Analyzed</div>
        </div>
        <div class="stat-tile">
          <div class="stat-number">{theme_count}</div>
          <div class="stat-label">Major Player Themes Found</div>
        </div>
      </div>
    </section>
    """


def hidden_strengths_section(gaps_data):
    items = gaps_data.get("hidden_strengths", [])
    rows = []
    for item in items:
        theme = esc(item.get("theme", ""))
        mentions = item.get("mention_count", 0)
        coverage = item.get("marketing_coverage", "minimal")
        quote = esc(item.get("evidence_quote", ""))
        rows.append(f"""
        <div class="card strength-card">
          <div class="card-header">
            <span class="card-title">{theme}</span>
            <span class="pill pill-strength">{mentions} mentions</span>
          </div>
          <div class="card-meta">Marketing coverage: <strong>{esc(coverage)}</strong></div>
          <blockquote>&ldquo;{quote}&rdquo;</blockquote>
        </div>
        """)
    body = "\n".join(rows) if rows else '<p class="empty">No hidden strengths found.</p>'
    return f"""
    <section id="hidden-strengths">
      <h2>What Players Value That Marketing Misses</h2>
      <p class="section-sub">Themes players bring up often and praise, but that marketing barely mentions.</p>
      <div class="card-grid">
        {body}
      </div>
    </section>
    """


def marketing_disconnects_section(gaps_data):
    items = gaps_data.get("marketing_disconnects", [])
    rows = []
    for item in items:
        claim_text = esc(item.get("claim_text", ""))
        claim_id = esc(item.get("claim_id", ""))
        discussion = esc(item.get("player_discussion", "none"))
        rows.append(f"""
        <div class="card disconnect-card">
          <div class="card-header">
            <span class="card-title">{claim_text}</span>
            <span class="pill pill-disconnect">{claim_id}</span>
          </div>
          <div class="card-meta">Player discussion: <strong>{discussion}</strong></div>
        </div>
        """)
    body = "\n".join(rows) if rows else '<p class="empty">No marketing disconnects found.</p>'
    return f"""
    <section id="marketing-disconnects">
      <h2>What Marketing Says That Players Rarely Mention</h2>
      <p class="section-sub">Marketing claims that find little to no echo in player reviews.</p>
      <div class="card-grid">
        {body}
      </div>
    </section>
    """


def vocabulary_section(vocab_data):
    review_terms = vocab_data.get("review_only_terms", [])[:12]
    marketing_terms = vocab_data.get("marketing_only_terms", [])[:12]
    same_idea = vocab_data.get("same_idea_different_words", [])

    review_chips = "\n".join(
        f'<span class="chip chip-review">{esc(t["term"])} <em>({t["review_count"]})</em></span>'
        for t in review_terms
    )
    marketing_chips = "\n".join(
        f'<span class="chip chip-marketing">{esc(t["term"])} <em>({t["marketing_count"]})</em></span>'
        for t in marketing_terms
    )

    idea_rows = "\n".join(f"""
        <tr>
          <td>{esc(pair.get("concept", ""))}</td>
          <td><span class="lang-marketing">&ldquo;{esc(pair.get("marketing_phrase", ""))}&rdquo;</span></td>
          <td><span class="lang-player">&ldquo;{esc(pair.get("player_phrase", ""))}&rdquo;</span></td>
        </tr>
        """ for pair in same_idea)

    return f"""
    <section id="vocabulary">
      <h2>Marketing Language vs Player Language</h2>
      <p class="section-sub">The same ideas, described in two very different vocabularies.</p>

      <div class="vocab-columns">
        <div class="vocab-col">
          <h3>Words Players Use (Marketing Doesn't)</h3>
          <div class="chip-row">{review_chips}</div>
        </div>
        <div class="vocab-col">
          <h3>Words Marketing Uses (Players Don't)</h3>
          <div class="chip-row">{marketing_chips}</div>
        </div>
      </div>

      <h3 class="table-heading">Same Idea, Different Words</h3>
      <table class="idea-table">
        <thead>
          <tr><th>Concept</th><th>Marketing Says</th><th>Players Say</th></tr>
        </thead>
        <tbody>
          {idea_rows}
        </tbody>
      </table>
    </section>
    """


SENTIMENT_CLASS = {
    "positive": "sentiment-positive",
    "negative": "sentiment-negative",
    "mixed": "sentiment-mixed",
}


def themes_section(themes_data):
    themes = themes_data.get("themes", [])
    cards = []
    for t in themes:
        sentiment = t.get("sentiment", "mixed")
        sentiment_class = SENTIMENT_CLASS.get(sentiment, "sentiment-mixed")
        keywords = ", ".join(esc(k) for k in t.get("keywords", []))
        cards.append(f"""
        <div class="card theme-card">
          <div class="card-header">
            <span class="card-title">{esc(t.get("theme", ""))}</span>
            <span class="pill {sentiment_class}">{esc(sentiment)}</span>
          </div>
          <div class="card-meta">{t.get("mention_count", 0)} mentions &middot; keywords: {keywords}</div>
        </div>
        """)
    body = "\n".join(cards) if cards else '<p class="empty">No themes found.</p>'
    return f"""
    <section id="themes">
      <h2>Major Player Themes</h2>
      <p class="section-sub">The most common topics players raise across reviews.</p>
      <div class="card-grid">
        {body}
      </div>
    </section>
    """


def quotes_section(themes_data):
    themes = themes_data.get("themes", [])
    blocks = []
    for t in themes:
        quotes = t.get("quotes", [])
        if not quotes:
            continue
        quote_items = "\n".join(f'<li>&ldquo;{esc(q)}&rdquo;</li>' for q in quotes)
        blocks.append(f"""
        <div class="quote-block">
          <h3>{esc(t.get("theme", ""))}</h3>
          <ul class="quote-list">
            {quote_items}
          </ul>
        </div>
        """)
    body = "\n".join(blocks) if blocks else '<p class="empty">No quotes found.</p>'
    return f"""
    <section id="quotes">
      <h2>Real Player Quotes</h2>
      <p class="section-sub">Direct quotes pulled from player reviews, grouped by theme.</p>
      {body}
    </section>
    """


CSS = """
    :root {
      --bg: #0f172a;
      --panel: #16213c;
      --panel-alt: #1c2846;
      --text: #f4f6fb;
      --text-dim: #b7c0d8;
      --accent: #5eead4;
      --accent-strong: #2dd4bf;
      --warn: #fbbf24;
      --bad: #fb7185;
      --good: #34d399;
      --mixed: #fbbf24;
      --border: #2c3a5e;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, Helvetica, sans-serif;
      font-size: 20px;
      line-height: 1.5;
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 40px 32px 100px;
    }
    header.hero {
      text-align: center;
      padding: 56px 24px 48px;
      border-bottom: 4px solid var(--accent-strong);
      margin-bottom: 48px;
    }
    header.hero h1 {
      font-size: 3rem;
      margin: 0 0 12px;
      letter-spacing: 0.5px;
    }
    header.hero .subtitle {
      font-size: 1.4rem;
      color: var(--text-dim);
      margin: 0;
    }
    nav.toc {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 12px;
      margin-top: 28px;
    }
    nav.toc a {
      color: var(--bg);
      background: var(--accent);
      text-decoration: none;
      font-weight: 600;
      padding: 10px 18px;
      border-radius: 999px;
      font-size: 1rem;
    }
    nav.toc a:hover { background: var(--accent-strong); }

    section {
      margin-bottom: 64px;
    }
    section h2 {
      font-size: 2.2rem;
      margin: 0 0 8px;
      border-left: 8px solid var(--accent-strong);
      padding-left: 16px;
    }
    .section-sub {
      color: var(--text-dim);
      font-size: 1.15rem;
      margin: 0 0 28px;
      padding-left: 24px;
    }

    .stat-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 24px;
    }
    .stat-tile {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 36px 24px;
      text-align: center;
    }
    .stat-number {
      font-size: 3.4rem;
      font-weight: 800;
      color: var(--accent);
    }
    .stat-label {
      font-size: 1.2rem;
      color: var(--text-dim);
      margin-top: 8px;
    }

    .card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 20px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 10px;
    }
    .card-title {
      font-size: 1.25rem;
      font-weight: 700;
    }
    .card-meta {
      color: var(--text-dim);
      font-size: 1rem;
      margin-bottom: 10px;
    }
    .pill {
      flex-shrink: 0;
      display: inline-block;
      padding: 5px 12px;
      border-radius: 999px;
      font-size: 0.9rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .pill-strength { background: rgba(52, 211, 153, 0.18); color: var(--good); }
    .pill-disconnect { background: rgba(251, 113, 133, 0.18); color: var(--bad); }
    .sentiment-positive { background: rgba(52, 211, 153, 0.18); color: var(--good); }
    .sentiment-negative { background: rgba(251, 113, 133, 0.18); color: var(--bad); }
    .sentiment-mixed { background: rgba(251, 191, 36, 0.18); color: var(--mixed); }

    blockquote {
      margin: 12px 0 0;
      padding: 12px 16px;
      border-left: 4px solid var(--accent-strong);
      background: var(--panel-alt);
      font-style: italic;
      font-size: 1.05rem;
      border-radius: 6px;
    }

    .vocab-columns {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 24px;
      margin-bottom: 40px;
    }
    .vocab-col h3 {
      font-size: 1.3rem;
      margin-bottom: 14px;
    }
    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .chip {
      display: inline-block;
      padding: 8px 14px;
      border-radius: 999px;
      font-size: 1.05rem;
      font-weight: 600;
    }
    .chip em {
      font-style: normal;
      opacity: 0.75;
      font-weight: 400;
      font-size: 0.9rem;
    }
    .chip-review { background: rgba(94, 234, 212, 0.15); color: var(--accent); border: 1px solid rgba(94, 234, 212, 0.4); }
    .chip-marketing { background: rgba(251, 191, 36, 0.15); color: var(--warn); border: 1px solid rgba(251, 191, 36, 0.4); }

    .table-heading {
      font-size: 1.3rem;
      margin: 8px 0 14px;
    }
    table.idea-table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border-radius: 14px;
      overflow: hidden;
    }
    table.idea-table th, table.idea-table td {
      text-align: left;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 1.05rem;
    }
    table.idea-table th {
      background: var(--panel-alt);
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
    }
    .lang-marketing { color: var(--warn); }
    .lang-player { color: var(--accent); }

    .quote-block {
      margin-bottom: 28px;
    }
    .quote-block h3 {
      font-size: 1.35rem;
      margin-bottom: 10px;
      color: var(--accent);
    }
    .quote-list {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 12px;
    }
    .quote-list li {
      background: var(--panel);
      border: 1px solid var(--border);
      border-left: 4px solid var(--accent-strong);
      border-radius: 10px;
      padding: 16px 20px;
      font-size: 1.1rem;
      font-style: italic;
    }

    .empty { color: var(--text-dim); font-style: italic; }

    footer {
      text-align: center;
      color: var(--text-dim);
      font-size: 0.95rem;
      margin-top: 60px;
      padding-top: 24px;
      border-top: 1px solid var(--border);
    }

    @media (max-width: 640px) {
      html, body { font-size: 17px; }
      header.hero h1 { font-size: 2.2rem; }
    }
"""


def build_html(reviews_data, marketing_data, themes_data, gaps_data, vocab_data):
    game_name = esc(reviews_data.get("game_name", "Unknown Game"))

    body_sections = "\n".join([
        summary_section(reviews_data, marketing_data, themes_data),
        hidden_strengths_section(gaps_data),
        marketing_disconnects_section(gaps_data),
        vocabulary_section(vocab_data),
        themes_section(themes_data),
        quotes_section(themes_data),
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{game_name} - Voice of Customer vs Marketing</title>
<style>
{CSS}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <h1>{game_name} &mdash; Voice of Customer vs Marketing</h1>
      <p class="subtitle">What players actually say, compared with what marketing actually claims.</p>
      <nav class="toc">
        <a href="#hidden-strengths">Hidden Strengths</a>
        <a href="#marketing-disconnects">Marketing Disconnects</a>
        <a href="#vocabulary">Vocabulary</a>
        <a href="#themes">Player Themes</a>
        <a href="#quotes">Player Quotes</a>
      </nav>
    </header>

    {body_sections}

    <footer>
      Generated entirely from local project data. No external services, network access, or
      additional files are required to view this report.
    </footer>
  </div>
</body>
</html>
"""


def main():
    reviews_data = load("reviews.json")
    marketing_data = load("marketing.json")
    themes_data = load("review_themes.json")
    gaps_data = load("gaps.json")
    vocab_data = load("vocabulary.json")

    html_out = build_html(reviews_data, marketing_data, themes_data, gaps_data, vocab_data)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html_out, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(html_out):,} bytes)")


if __name__ == "__main__":
    main()
