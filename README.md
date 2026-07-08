# Augerer Tarot (Flask)

Tarot app with two core features:

1. AI-powered readings — draw a single card or a past / present / future
   three-card spread and get a witchy interpretation streamed live.
2. Look up card meanings by name and open a dedicated detail page.

The UI reuses core Astro styling/ambient JS assets for a near-identical visual feel.
Each card has a generated SVG image under `static/cards`.

## Run

1. Create and activate your Python environment.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Configure the Anthropic token used for AI readings (see below).

4. Start Flask:

```powershell
python app.py
```

5. Open:

http://127.0.0.1:5000

## AI readings

Readings stream from Anthropic Claude (model `claude-haiku-4-5`). Set an
`ANTHROPIC_TOKEN` environment variable, either in your shell or in a local
`.env` file (loaded automatically via `python-dotenv`):

```
ANTHROPIC_TOKEN=sk-ant-...
```

Without a token the reading pages still render, but the interpretation endpoint
returns a friendly "reader unavailable" message instead of streaming text.

Reading behavior is driven by editable prompt files in `prompts/`:

- `reading_system.md` — the reader's system voice.
- `one_card_user.md` — the single-card prompt.
- `three_card_user.md` — the three-card (past / present / future) prompt.

## Tests

```powershell
python -m pytest
```

## Card art

Each card renders from an SVG under `static/cards`. Selected FreeSVG source URLs
are recorded in `data/freesvg_card_sources.json`. Reversed draws show the art
upside-down and overlay the reversed meaning text.
