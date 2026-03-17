# GitHub Trending → Telegram (Gemini-powered)

Get a daily GitHub Trending digest delivered to Telegram, enriched with a practical “Why does this matter to me?” explanation powered by Gemini.

- **Cost-controlled**: processes only the **top 5** trending repos
- **Useful**: uses repo description + README excerpt to generate concrete ideas
- **Readable**: posts **one repo per message** with bold section headings

## Quick start

### Clone

```bash
git clone https://github.com/susayanokyanus/gh-trends-digest.git
cd gh-trends-digest
```

### Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Optional (recommended): Gemini enrichment
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-flash-latest
```

## What you’ll receive on Telegram

Each run sends:
- 1 header message (date + scope)
- 5 repo messages (top 5 trending), each containing:
  - Description + today’s stars
  - **Özet** (3–4 sentences)
  - **Fikirler** (exactly 4 single-sentence ideas; never omitted)
  - Repo link

## Run locally

```bash
./venv/bin/python main.py
```

## Run daily with GitHub Actions

This repo includes a scheduled workflow: `.github/workflows/daily.yml`.

### Add repository secrets

In GitHub: **Settings → Secrets and variables → Actions**

Add:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` (optional)
- `GEMINI_MODEL` (optional, recommended: `gemini-flash-latest`)

### Test manually

Go to **Actions → Daily GitHub Trending Digest → Run workflow**.

## Notes

- `.env` is ignored by git (do not commit secrets).
- If your Gemini model name returns 404, set `GEMINI_MODEL=gemini-flash-latest` in Secrets/env.


