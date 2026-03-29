# LinkedIn DM Bot

A Python automation bot for LinkedIn Messaging that extracts conversations, messages, and attachments to a local SQLite database.

## Approach

- Uses the LinkedIn **mobile web UI** (iPhone 5/SE 320×568 viewport, iOS 10 UA) — simpler DOM, fewer anti-bot measures
- Navigates via **ARIA roles and accessible names**, not CSS selectors
- Runs **headless by default**, falling back to a visible browser automatically if a navigation error or checkpoint is detected
- Stores everything in **SQLite** for idempotent, incremental syncing
- Built-in **rate limiting** with random human-like delays

## Installation

```bash
# Install dependencies
uv sync

# Install Playwright browser
uv run playwright install chromium

# Configure credentials
cp .env .env.local   # or edit .env directly
```

## Configuration

`.env` variables:

```bash
# Required
LI_USER=your_email@example.com
LI_PASS=your_password

# Optional — defaults shown
DM_BOT_PROFILE_PATH=.persistence/browser_profile
DM_BOT_DB_PATH=.persistence/dm_bot.db
DM_BOT_LOG_LEVEL=INFO
DM_BOT_HEADLESS=true
DM_BOT_DELAY_MIN=2.0
DM_BOT_DELAY_MAX=5.0
DM_BOT_MAX_ACTIONS_PER_MINUTE=20
```

All runtime state (browser profile, database, attachments) lives under `.persistence/` in the repo root, which is git-ignored.

## CLI Commands

### `dm-bot login`

Open a browser window for manual LinkedIn login. Run this once to save your session.

```bash
uv run dm-bot login
uv run dm-bot login --profile /custom/path   # custom profile dir
```

### `dm-bot navigate`

Test that the bot can reach the LinkedIn messaging interface. Useful for verifying session health.

```bash
uv run dm-bot navigate
```

### `dm-bot sync`

Sync the N most recent conversations from your LinkedIn inbox to the local database. For each message, also downloads file attachments and scrapes any outbound links.

```bash
uv run dm-bot sync                        # default: up to 50 conversations
uv run dm-bot sync --limit 10             # limit to 10 conversations
uv run dm-bot sync --since 2025-01-01     # only conversations active after date
uv run dm-bot sync --limit 10 --since 2025-01-01
```

**Options:**
- `--limit, -l N` — max conversations to process (default: 50)
- `--since, -s DATE` — ISO date filter on `last_message_at` (default: 30 days ago)
- `--profile, -p PATH` — custom browser profile directory

**What it does per conversation:**
1. Extracts messages via DOM (Layout A or Layout B depending on LinkedIn render)
2. Downloads any file attachments (`.docx`, `.pdf`, etc.) to `.persistence/attachments/`
3. Scrapes outbound URLs using `trafilatura` and saves extracted text to `.persistence/attachments/`
4. Deduplicates — re-running is safe

**Progress output:**
```
Processing 1/10: Jane Smith
  Found 8 messages
  Stored 8 new, skipped 0 duplicates
Processing 2/10: Recruiter Name
  Found 3 messages
  Saved attachment: .persistence/attachments/17_job_spec.docx (42,100 bytes)
  Scraped and saved: .persistence/attachments/17_web_0_example.com.txt (3,200 bytes)
  Stored 3 new, skipped 0 duplicates
...
============================================================
Sync Complete
============================================================
Conversations processed: 10
Messages stored: 42
Messages skipped (duplicates): 8
Time elapsed: 0:02:15
```

### `dm-bot sync-conversation`

Sync a single conversation by its thread URL. Useful for re-syncing or testing.

```bash
uv run dm-bot sync-conversation https://www.linkedin.com/messaging/thread/2-xxx/
```

### `dm-bot dump`

Display stored messages. Useful for debugging and verifying sync output.

```bash
uv run dm-bot dump                                    # all messages (up to 100)
uv run dm-bot dump --conversation john-doe-12345      # filter by connection slug
uv run dm-bot dump --limit 500
```

### `dm-bot inbox`

List recent conversations, sorted by last message time.

```bash
uv run dm-bot inbox              # conversations active in the last 7 days
uv run dm-bot inbox --since 14   # last 14 days
```

**Options:**
- `--since, -s N` — number of days to look back (default: 7)

### `dm-bot conversation`

Print the full message thread for a conversation.

```bash
uv run dm-bot conversation <id>
```

The `<id>` is the connection slug shown in `inbox` output.

### `dm-bot find`

Search for a conversation by contact name.

```bash
uv run dm-bot find "Jane Smith"
uv run dm-bot find jane            # partial match
```

### `dm-bot get-url`

Get the LinkedIn thread URL for a conversation by connection slug.

```bash
uv run dm-bot get-url <id>
```

### `dm-bot send-message`

Send a message to a conversation, with an optional file attachment.

```bash
uv run dm-bot send-message <id> "Your message here"
uv run dm-bot send-message <id> "Please find my CV attached" --attachment /path/to/file.docx
```

**Options:**
- `--attachment, -a PATH` — path to a file to attach (e.g. a PDF or DOCX)

After sending, the conversation is automatically re-synced so the outbound message appears in the local database.

### `dm-bot dump-tree`

Capture the accessibility tree snapshot for a LinkedIn URL and save it as JSON to `.dm_bot_debug/`. Used during development to understand LinkedIn's DOM structure.

```bash
uv run dm-bot dump-tree                                          # LinkedIn home
uv run dm-bot dump-tree --url https://www.linkedin.com/messaging/
uv run dm-bot dump-tree --prefix my_snapshot                     # custom filename prefix
uv run dm-bot dump-tree --output ./my_debug_dir                  # custom output dir
```

## Attachments & Link Scraping

During `sync`, for every new message the bot:

1. **File attachments** — finds `<a aria-label="Download ...">` elements inside the message DOM, downloads the file via `fetch()` using the browser's cookie jar, and saves it as `.persistence/attachments/{message_id}_{original_filename}`.

2. **Link scraping** — extracts outbound `<a href>` links from the message DOM, dereferences LinkedIn safety interstitials (`linkedin.com/safety/go?url=...`), then uses `trafilatura` to fetch and extract the main text content. Saves as `.persistence/attachments/{message_id}_web_{n}_{domain}.txt`. Pages that require JavaScript (SPAs) are silently skipped.

Both are stored in the `attachment` table linked to their message.

## Database

SQLite at `.persistence/dm_bot.db`. Schema:

| Table          | Description                                                  |
|----------------|--------------------------------------------------------------|
| `connection`   | LinkedIn users (slug, display name, profile URL)             |
| `conversation` | Message threads (connection FK, thread URL, sync timestamps) |
| `message`      | Individual messages (content, timestamp, direction, dedup key) |
| `attachment`   | Files linked to messages (path on disk, original filename, size) |

Deduplication key: `SHA256(conversation_id | content | direction)` — re-syncing the same message is always a no-op.

## Rate Limiting

| Parameter              | Default | Env var                      |
|------------------------|---------|------------------------------|
| Delay between actions  | 2–5s    | `DM_BOT_DELAY_MIN/MAX`       |
| Max actions per minute | 20      | `DM_BOT_MAX_ACTIONS_PER_MINUTE` |
| Post-page-load wait    | 1.5–3s  | —                            |

## Troubleshooting

**Login / checkpoint issues**
- Run `uv run dm-bot login` and complete any security checks manually
- Keep the browser open until you see "Login successful"

**Sync stops with checkpoint**
- The bot will automatically relaunch with a visible browser when it detects a checkpoint
- Complete the checkpoint in the browser window, then the flow will retry automatically

**Rate limiting**
- Increase `DM_BOT_DELAY_MIN` / `DM_BOT_DELAY_MAX` in `.env`
- Reduce `--limit` to process fewer conversations per run

**Platform**
- macOS only (uses `osascript` for desktop notifications)
