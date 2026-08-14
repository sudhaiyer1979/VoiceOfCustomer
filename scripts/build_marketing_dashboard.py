#!/usr/bin/env python3
"""Voice of Customer - WS8: Marketing Dashboard.

Reads data/marketing_insights.json (plus gaps.json and vocabulary.json for
the vocabulary/evidence sections) and writes a single, self-contained HTML
file to output/marketing_dashboard.html -- no external dependencies, no
server, opens directly in a browser.

This is the marketer-facing counterpart to build_dashboard.py: it never
shows raw machine-generated theme names as headings, only the human-readable
customer_perception statements from marketing_insights.json.
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output" / "marketing_dashboard.html"


def load(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return json.load(f)


def esc(text):
    return html.escape(str(text), quote=True)


ACTION_CLASS = {
    "ADD": "action-add",
    "KEEP": "action-keep",
    "REDUCE": "action-reduce",
    "REFRAME": "action-reframe",
}

ALIGNMENT_CLASS = {
    "ALIGNED": "align-aligned",
    "UNDERREPRESENTED": "align-under",
    "OVEREMPHASIZED": "align-over",
}


def next_steps_section(insights_data):
    recs = insights_data.get("top_recommendations", [])
    cards = []
    for r in recs:
        action = r.get("action", "")
        action_class = ACTION_CLASS.get(action, "action-keep")
        cards.append(f"""
        <div class="card rec-card">
          <div class="card-header">
            <span class="pill {action_class}">{esc(action)}</span>
            <span class="card-title">{esc(r.get("title", ""))}</span>
          </div>
          <p class="rec-detail">{esc(r.get("detail", ""))}</p>
        </div>
        """)
    body = "\n".join(cards) if cards else '<p class="empty">No recommendations available.</p>'
    return f"""
    <section id="next-steps">
      <h2>What Marketing Should Do Next</h2>
      <p class="section-sub">Concrete actions, ranked by what moves the needle on how customers see the brand.</p>
      <div class="card-grid">
        {body}
      </div>
    </section>
    """


def perceptions_section(insights_data):
    perceptions = insights_data.get("perceptions", [])
    cards = []
    for p in perceptions:
        alignment = p.get("alignment", "")
        align_class = ALIGNMENT_CLASS.get(alignment, "align-aligned")
        cards.append(f"""
        <div class="card perception-card">
          <div class="card-header">
            <span class="card-title">{esc(p.get("customer_perception", ""))}</span>
            <span class="pill {align_class}">{esc(alignment)}</span>
          </div>
          <div class="perception-row">
            <div class="perception-col">
              <div class="perception-label">Current marketing position</div>
              <p>{esc(p.get("current_marketing_position", ""))}</p>
            </div>
            <div class="perception-col">
              <div class="perception-label">Recommended action</div>
              <p>{esc(p.get("recommended_action", ""))}</p>
            </div>
          </div>
          <div class="perception-label">Suggested messaging direction</div>
          <p class="messaging">{esc(p.get("suggested_messaging", ""))}</p>
        </div>
        """)
    body = "\n".join(cards) if cards else '<p class="empty">No customer perceptions available.</p>'
    return f"""
    <section id="how-customers-see-brand">
      <h2>How Customers See The Brand</h2>
      <p class="section-sub">What real players believe about this game, translated out of internal analysis labels.</p>
      <div class="card-grid">
        {body}
      </div>
    </section>
    """


def alignment_section(insights_data):
    perceptions = insights_data.get("perceptions", [])
    groups = {"UNDERREPRESENTED": [], "ALIGNED": [], "OVEREMPHASIZED": []}
    for p in perceptions:
        groups.setdefault(p.get("alignment", ""), []).append(p)

    titles = {
        "UNDERREPRESENTED": "Underrepresented — players feel this, marketing barely says it",
        "ALIGNED": "Aligned — marketing matches what players say",
        "OVEREMPHASIZED": "Overemphasized — marketing pushes this harder than players talk about it",
    }

    columns = []
    for key in ("UNDERREPRESENTED", "ALIGNED", "OVEREMPHASIZED"):
        items = groups.get(key, [])
        rows = "\n".join(
            f'<li>{esc(p.get("customer_perception", ""))}</li>' for p in items
        ) or '<li class="empty">None</li>'
        align_class = ALIGNMENT_CLASS.get(key, "align-aligned")
        columns.append(f"""
        <div class="alignment-col">
          <h3 class="pill {align_class}">{esc(titles[key])}</h3>
          <ul class="alignment-list">
            {rows}
          </ul>
        </div>
        """)

    return f"""
    <section id="brand-alignment">
      <h2>Brand Alignment</h2>
      <p class="section-sub">Every customer perception, grouped by whether marketing over-, under-, or correctly represents it.</p>
      <div class="alignment-columns">
        {"".join(columns)}
      </div>
    </section>
    """


def vocabulary_section(vocab_data):
    review_terms = vocab_data.get("review_only_terms", [])[:12]
    marketing_terms = vocab_data.get("marketing_only_terms", [])[:12]
    same_idea = vocab_data.get("same_idea_different_words", [])

    review_chips = "\n".join(
        f'<span class="chip chip-review">{esc(t["term"])}</span>' for t in review_terms
    )
    marketing_chips = "\n".join(
        f'<span class="chip chip-marketing">{esc(t["term"])}</span>' for t in marketing_terms
    )

    idea_rows = "\n".join(f"""
        <tr>
          <td>{esc(pair.get("concept", ""))}</td>
          <td><span class="lang-marketing">&ldquo;{esc(pair.get("marketing_phrase", ""))}&rdquo;</span></td>
          <td><span class="lang-player">&ldquo;{esc(pair.get("player_phrase", ""))}&rdquo;</span></td>
        </tr>
        """ for pair in same_idea)

    return f"""
    <section id="speak-like-customers">
      <h2>Speak Like Your Customers</h2>
      <p class="section-sub">The words players actually use, versus the words marketing currently uses.</p>
      <div class="vocab-columns">
        <div class="vocab-col">
          <h3>Borrow These Player Words</h3>
          <div class="chip-row">{review_chips}</div>
        </div>
        <div class="vocab-col">
          <h3>Marketing-Only Language</h3>
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


def evidence_section(insights_data):
    perceptions = insights_data.get("perceptions", [])
    items = []
    for p in perceptions:
        quote = p.get("evidence_quote", "")
        if not quote:
            continue
        items.append(f"""
        <div class="evidence-block">
          <blockquote>&ldquo;{esc(quote)}&rdquo;</blockquote>
          <div class="evidence-meta">Supports: {esc(p.get("customer_perception", ""))}</div>
        </div>
        """)
    body = "\n".join(items) if items else '<p class="empty">No evidence quotes available.</p>'
    return f"""
    <section id="evidence">
      <h2>Evidence</h2>
      <p class="section-sub">Verbatim player quotes behind every perception above.</p>
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
      --border: #2c3a5e;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0; padding: 0;
      background: var(--bg); color: var(--text);
      font-family: "Segoe UI", Arial, Helvetica, sans-serif;
      font-size: 20px; line-height: 1.5;
    }
    .wrap { max-width: 1200px; margin: 0 auto; padding: 40px 32px 100px; }
    header.hero {
      text-align: center; padding: 56px 24px 48px;
      border-bottom: 4px solid var(--accent-strong); margin-bottom: 48px;
    }
    header.hero h1 { font-size: 2.8rem; margin: 0 0 12px; }
    header.hero .subtitle { font-size: 1.3rem; color: var(--text-dim); margin: 0; }
    nav.toc { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; margin-top: 28px; }
    nav.toc a {
      color: var(--bg); background: var(--accent); text-decoration: none;
      font-weight: 600; padding: 10px 18px; border-radius: 999px; font-size: 1rem;
    }
    nav.toc a:hover { background: var(--accent-strong); }
    section { margin-bottom: 64px; }
    section h2 {
      font-size: 2.1rem; margin: 0 0 8px;
      border-left: 8px solid var(--accent-strong); padding-left: 16px;
    }
    .section-sub { color: var(--text-dim); font-size: 1.1rem; margin: 0 0 28px; padding-left: 24px; }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; }
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 24px; }
    .card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
    .card-title { font-size: 1.2rem; font-weight: 700; }
    .pill {
      flex-shrink: 0; display: inline-block; padding: 5px 12px; border-radius: 999px;
      font-size: 0.85rem; font-weight: 700; white-space: nowrap;
    }
    .action-add { background: rgba(52, 211, 153, 0.18); color: var(--good); }
    .action-keep { background: rgba(94, 234, 212, 0.18); color: var(--accent); }
    .action-reduce { background: rgba(251, 113, 133, 0.18); color: var(--bad); }
    .action-reframe { background: rgba(251, 191, 36, 0.18); color: var(--warn); }
    .align-aligned { background: rgba(52, 211, 153, 0.18); color: var(--good); }
    .align-under { background: rgba(251, 191, 36, 0.18); color: var(--warn); }
    .align-over { background: rgba(251, 113, 133, 0.18); color: var(--bad); }
    .rec-detail { color: var(--text-dim); font-size: 1.02rem; margin: 6px 0 0; }
    .perception-row { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 14px 0; }
    .perception-label { color: var(--text-dim); font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }
    .perception-col p, .messaging { margin: 0; font-size: 1.02rem; }
    .messaging { font-style: italic; color: var(--accent); }
    .alignment-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
    .alignment-col h3 {
      display: block; width: 100%; margin: 0 0 14px; font-size: 0.95rem;
      white-space: normal; line-height: 1.35; text-align: left;
    }
    .alignment-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
    .alignment-list li {
      background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
      padding: 12px 16px; font-size: 1rem;
    }
    .alignment-list li.empty { color: var(--text-dim); font-style: italic; background: none; border: none; }
    .vocab-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 24px; margin-bottom: 40px; }
    .vocab-col h3 { font-size: 1.25rem; margin-bottom: 14px; }
    .chip-row { display: flex; flex-wrap: wrap; gap: 10px; }
    .chip { display: inline-block; padding: 8px 14px; border-radius: 999px; font-size: 1.02rem; font-weight: 600; }
    .chip-review { background: rgba(94, 234, 212, 0.15); color: var(--accent); border: 1px solid rgba(94, 234, 212, 0.4); }
    .chip-marketing { background: rgba(251, 191, 36, 0.15); color: var(--warn); border: 1px solid rgba(251, 191, 36, 0.4); }
    .table-heading { font-size: 1.25rem; margin: 8px 0 14px; }
    table.idea-table { width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 14px; overflow: hidden; }
    table.idea-table th, table.idea-table td { text-align: left; padding: 14px 18px; border-bottom: 1px solid var(--border); font-size: 1.02rem; }
    table.idea-table th { background: var(--panel-alt); font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); }
    .lang-marketing { color: var(--warn); }
    .lang-player { color: var(--accent); }
    .evidence-block { margin-bottom: 18px; }
    blockquote {
      margin: 0; padding: 14px 18px; border-left: 4px solid var(--accent-strong);
      background: var(--panel); font-style: italic; font-size: 1.05rem; border-radius: 6px;
    }
    .evidence-meta { color: var(--text-dim); font-size: 0.95rem; margin: 6px 0 0 18px; }
    .empty { color: var(--text-dim); font-style: italic; }
    footer {
      text-align: center; color: var(--text-dim); font-size: 0.95rem;
      margin-top: 60px; padding-top: 24px; border-top: 1px solid var(--border);
    }
    @media (max-width: 640px) {
      html, body { font-size: 17px; }
      header.hero h1 { font-size: 2rem; }
      .perception-row { grid-template-columns: 1fr; }
    }
"""


def build_html(insights_data, gaps_data, vocab_data):
    game_name = esc(insights_data.get("game_name", "Unknown Game"))

    body_sections = "\n".join([
        next_steps_section(insights_data),
        perceptions_section(insights_data),
        alignment_section(insights_data),
        vocabulary_section(vocab_data),
        evidence_section(insights_data),
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{game_name} - Brand Perception Dashboard</title>
<style>
{CSS}
</style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <h1>{game_name} &mdash; Brand Perception Dashboard</h1>
      <p class="subtitle">What customers believe, what marketing says, and what to do about the gap.</p>
      <nav class="toc">
        <a href="#next-steps">Next Steps</a>
        <a href="#how-customers-see-brand">Customer Perceptions</a>
        <a href="#brand-alignment">Brand Alignment</a>
        <a href="#speak-like-customers">Speak Like Your Customers</a>
        <a href="#evidence">Evidence</a>
      </nav>
    </header>

    {body_sections}

    <footer>
      Generated entirely from real customer review and marketing data. No external services or
      additional files are required to view this report.
    </footer>
  </div>
</body>
</html>
"""


def main():
    insights_data = load("marketing_insights.json")
    gaps_data = load("gaps.json")
    vocab_data = load("vocabulary.json")

    html_out = build_html(insights_data, gaps_data, vocab_data)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html_out, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(html_out):,} bytes)")


if __name__ == "__main__":
    main()
