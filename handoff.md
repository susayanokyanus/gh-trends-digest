## Project Handoff (for another AI/model)

This document captures **what we built, why, and how it works**, so another AI model (or future you) can continue development without re-discovering context.

### What the bot does

- Scrapes GitHub Trending (`https://github.com/trending`)
- Picks **top 5 repositories** (cost control)
- For each repo, produces a Turkish answer to: **“Bu benim ne işime yarar?”**
  - Short **summary** (3–4 sentences)
  - Up to / exactly **4 actionable ideas**
- Sends results to Telegram as:
  - **1 header message**
  - **5 separate repo messages** (readability + avoids truncation)

### Key product requirements we implemented

- **Cost control**: only top 5 repos are processed per run.
- **Readable Telegram formatting**: bold section headers, consistent layout.
- **Never omit ideas**: output must always include an “Ideas/Fikirler” section.
- **Defensive against LLM quirks**: parse/normalize LLM output to avoid half-finished bullets.

### Runtime environments

- **Local**: run via `./venv/bin/python main.py`
- **Scheduled**: GitHub Actions workflow runs daily (`.github/workflows/daily.yml`)

### Configuration (env / GitHub Actions Secrets)

Required:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` (DM or group/channel id)

Optional (Gemini enrichment):
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
  - In practice, `gemini-flash-latest` worked for this account (other model names can 404).

Debug:
- `GEMINI_DEBUG=1` prints model fallback attempts and errors (useful in Actions logs).

### Data flow (high level)

1) **Fetch** trending HTML from GitHub.
2) **Parse** repositories via BeautifulSoup:
   - `full_name` (`owner/repo`)
   - `url`
   - `description`
   - `language`
   - `stars_today`
3) **Fetch README excerpt** (best effort):
   - tries `main/master` + common README filenames
   - source: `raw.githubusercontent.com`
4) **LLM enrichment** (if `GEMINI_API_KEY` present):
   - Calls Gemini REST endpoint using `x-goog-api-key` header (not query param).
   - Has model fallback logic (handles 404 for some model names).
5) **Strict output normalization**:
   - Parse Gemini response into `Özet:` and bullet ideas (`• ...`)
   - Normalize:
     - summary becomes **3–4 sentences**
     - ideas become **exactly 4** single-sentence bullets (trim/complete punctuation)
   - If Gemini output is malformed:
     - retry with a stricter prompt
     - if still not good → fallback ideas generated from rule-based categories
6) **Telegram delivery**:
   - Messages are sent with `parse_mode=HTML` and content is HTML-escaped.
   - Long messages are split to avoid Telegram size limits.
   - Each repo is posted as a separate message for readability.

### Why we chose “per-repo message” delivery

Telegram has message size limits and long content became hard to scan. Splitting by repo:
- avoids truncation
- improves readability in a channel
- makes it easier to forward or discuss a single repo

### Known constraints / edge cases

- GitHub Trending HTML can change; parsing selectors might need updates.
- Some repos do not have a standard README on `main/master`, so README excerpt may be empty.
- Gemini model names vary by account; model fallback is necessary.
- GitHub Actions runs in UTC; schedule may need adjustment for your timezone.

### Suggested future improvements

- Add Trending filters (language, daily/weekly/monthly).
- Cache results per-day to avoid re-sending duplicates.
- Better README excerpt selection (heuristics to pick “Usage/Install/Quickstart” sections).
- Rate limiting/backoff for Telegram broadcast channels with many subscribers.

