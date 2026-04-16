# LinkedIn DM Bot

A Python automation bot for LinkedIn Messaging that extracts conversations, messages, and attachments to a local SQLite database. Includes a companion career manager CLI for tracking recruiter leads and interview pipelines.

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

### `dm-bot logs`

Query the structured log table (logs are persisted to SQLite alongside the message database).

```bash
uv run dm-bot logs                              # recent log entries
uv run dm-bot logs --runs                       # summary of recent CLI runs
uv run dm-bot logs --command sync --limit 20    # filter by command
uv run dm-bot logs --errors-only                # only ERROR/CRITICAL
uv run dm-bot logs --run-id <uuid>              # entries for a specific run
```

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
| `log`          | Structured log entries (run_id, command, level, message, exc_text) |

Deduplication key: `SHA256(conversation_id | content | direction)` — re-syncing the same message is always a no-op.

## Rate Limiting

| Parameter              | Default | Env var                      |
|------------------------|---------|------------------------------|
| Delay between actions  | 2–5s    | `DM_BOT_DELAY_MIN/MAX`       |
| Max actions per minute | 20      | `DM_BOT_MAX_ACTIONS_PER_MINUTE` |
| Post-page-load wait    | 1.5–3s  | —                            |

## Career Manager

A companion CLI (`career`) for tracking recruiter leads and interview pipelines. Designed to work alongside `dm-bot` — when a recruiter reaches out on LinkedIn, you create a lead and track the process through to offer/decline.

### Setup

The career manager expects a directory at `~/CAREER/` (hardcoded for now — TODO: make this a config variable). The SQLite database is created automatically at `~/CAREER/career.db`.

### `career pipeline`

Dashboard of all active leads with their latest interview stage.

```bash
uv run career pipeline
```

### `career lead`

CRUD operations for recruiter leads.

```bash
uv run career lead create --company "Acme Corp" --role "Senior Engineer" --source linkedin --source-ref 42 --salary-min 120 --salary-max 150 --notes "Via recruiter Jane"
uv run career lead list                          # all leads
uv run career lead list --status active          # filter by status
uv run career lead show <id>                     # full details + process stages
uv run career lead update <id> --status declined --notes "Role filled"
```

**Lead statuses:** `active`, `declined`, `on_hold`, `closed`, `offer_accepted`

### `career process`

Track interview stages for a lead.

```bash
uv run career process add <lead_id> --stage recruiter_screen --scheduled 2025-04-21T14:00:00 --notes "30 min intro"
uv run career process list <lead_id>
uv run career process update <process_id> --status completed --outcome "Moving to technical"
```

**Stages:** `initial_call`, `recruiter_screen`, `hiring_manager`, `technical_interview`, `take_home`, `onsite`, `final_round`, `offer`, `negotiation`

**Process statuses:** `upcoming`, `completed`, `cancelled`, `rescheduled`, `no_show`

### Database

SQLite at `~/CAREER/career.db`. Schema:

| Table     | Description                                                        |
|-----------|--------------------------------------------------------------------|
| `lead`    | Companies/roles (status, salary band, source, notes)               |
| `process` | Interview stages per lead (stage type, scheduled time, outcome)    |

## Resume Builder

The recruiter workflow relies on [resume-build](https://github.com/faiz95ahmed/resume-builder) — a CLI tool that generates `.docx` resumes from a JSON source of truth. This enables tailoring CVs per opportunity without maintaining multiple Word documents by hand.

```bash
# Install globally
uv tool install git+ssh://git@github.com/faiz95ahmed/resume-builder

# Build a DOCX from JSON
resume-build build ~/CAREER/resume.json ~/CAREER/resume.docx

# Tailor for a specific role: copy, edit the JSON, then build
cp ~/CAREER/resume.json ~/CAREER/resume_acme.json
# ... edit resume_acme.json to emphasise relevant experience ...
resume-build build ~/CAREER/resume_acme.json ~/CAREER/resume_acme.docx
```

The canonical untailored resume lives at `~/CAREER/resume.json`. Tailored variants follow the pattern `resume_<descriptor>.json` / `resume_<descriptor>.docx`.

## Email Integration

This project works best when paired with a CLI tool for sending and reading email, since many recruiter workflows move from LinkedIn to email for scheduling calls, sharing JDs, and follow-ups.

We use [gws](https://github.com/nicholasgasior/gws) — a CLI wrapper around Google Workspace APIs — for Gmail and Google Calendar access. Any tool that lets you send/read email from the command line would work, but the workflows in `CLAUDE.md` assume `gws` is available.

Key capabilities this enables:
- **Sending CVs and follow-ups via email** when a recruiter provides their address
- **Reading inbound JDs and scheduling emails** without leaving the terminal
- **Calendar integration** for checking availability and booking interview slots

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
