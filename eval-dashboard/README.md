# Credit Union Review Labeling Eval

A standalone tool built for the "Labeling Reviews with LLMs" in-class exercise. Not part
of the Voice of Customer Steam-review pipeline described in the repo's `CLAUDE.md` — this
labels 5 credit-union member reviews and compares your hand labels against two LLMs of
your choice.

## Run it

Open `index.html` directly in a browser (double-click it, or `file://` it). No server,
no build step, no dependencies.

## Data

The 5 reviews are embedded directly in `index.html`, sourced from
`data/credit_union_reviews.xlsx`.

## Usage

1. Read each review and record your own sentiment + topic label, then click
   "Submit my labels" (locks them so you can't peek at model output while still labeling).
2. Pick a provider and model ID for Model A and Model B, and paste in your own API
   key for each (used only for direct browser calls to that provider — never written to
   disk or hard-coded).
3. Edit the classification prompt if you like, then "Run both models on all 5 reviews".
4. Read the review-by-review comparison and each model's sentiment / topic / overall
   agreement score against your labels.
5. Optionally export the full results to CSV.

Supported providers: OpenAI, Anthropic, Google (Gemini), OpenRouter.
