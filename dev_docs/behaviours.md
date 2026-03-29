# Behavioural Requirements

These are the invariants the system must uphold. They were originally defined as acceptance criteria across the feature specs and should not regress.

---

## Storage

### Connections
- A new connection record is created when a previously unseen `linkedin_slug` is encountered
- An existing connection (same slug) is updated in place — `id` is preserved to avoid breaking conversation foreign keys
- Querying by `linkedin_slug` returns the record or `None`
- `list_all()` returns connections ordered by `updated_at DESC`

### Conversations
- One conversation per connection (1:1); upsert on `connection_id`
- `get_by_thread_url` does a prefix match (ignores `?trk=` query params)
- `last_message_at` is updated from actual stored message timestamps after sync
- `last_synced_at` is updated after each successful conversation sync

### Messages
- Deduplication key: `SHA256(f"{conversation_id}|{content}|{direction}")` — timestamp intentionally excluded to survive re-syncs with unreliable timestamps
- Storing the same message twice returns the existing record without inserting
- Messages are returned ordered by `timestamp ASC`
- Direction is `'inbound'` or `'outbound'` — enforced by a CHECK constraint

### Attachments
- One attachment record per file on disk; `attachment_path` is UNIQUE
- Storing the same path twice is idempotent (returns existing record)
- Filename on disk: `{message_id}_{original_filename}` — deterministic, no UUID
- Scraped web pages stored as `{message_id}_web_{n}_{domain}.txt` with `content_type='text/plain'`

### Database initialisation
- Schema uses `CREATE TABLE IF NOT EXISTS` throughout — safe to call `initialize_schema()` multiple times
- DB path is configurable via `DM_BOT_DB_PATH` env var; defaults to `.persistence/dm_bot.db` inside the repo

---

## Extraction & Sync

### Conversation discovery
- Inbox list items are parsed for connection name, snippet, and timestamp
- Thread URLs are enriched via DOM query (`document.querySelectorAll('ul li a')`) after accessibility snapshot

### Connection info
- Display name comes from the `heading` inside the `banner`, not the banner itself (which is truncated)
- If `linkedin_slug` is not extractable from DOM, it is generated from the display name
- If a thread URL matches an existing conversation belonging to a different connection, the conversation is re-linked to the correct connection

### Message extraction
- DOM-based extraction is preferred over scroll-based (more reliable)
- Before extracting, the conversation is scrolled to the top so all date separators are present in the DOM
- Layout A (`li.msg-s-message-list__event`) and Layout B (`li.member-message`) are both supported
- Time-separator items (body matches `HH:MM` or `H:MM AM/PM`) are paired with the preceding real message, not stored as standalone messages
- Profile card list items (>150 chars containing "1st"/"2nd"/"Premium member") are filtered out
- Attachment-only messages (no text body) get a synthesised body: `[attachment: {filename}]`

### Timestamps
- `_parse_dom_timestamp` handles: ISO datetime, ISO date-only, `"Mar 20"`, `"Mar 20, 2025"`, day-of-week (`"Monday"`), `"Today"`, `"Yesterday"`, and 12h/24h time strings
- Timestamps are resolved in a single forward pass (DOM order = oldest → newest):
  - Date separators update `running_date`
  - Messages with an explicit time get `running_date + that time`
  - Messages without a time are accumulated; when the next timed message is reached, it gets that time and earlier messages in the group are back-filled at `t - 1s`, `t - 2s`, etc. (LinkedIn only shows the timestamp on the last message in a consecutive group)
  - Any messages still pending after the pass (no subsequent time anchor) are placed after the last known timestamp at `+1s` intervals

### Deduplication in sync loop
- `get_by_conversation` is called before each store to check for existing dedup key — re-running sync on an already-synced conversation stores 0 new messages

### Attachments during sync
- File attachments are downloaded via `page.evaluate(fetch(...))` — uses the browser's cookie jar
- LinkedIn safety interstitials (`/safety/go?url=...`, `/redir/redirect?url=...`) are dereferenced before scraping
- `linkedin.com` URLs are skipped after dereferencing
- trafilatura failures (JS SPAs, network errors) are logged as warnings and do not abort the sync

---

## Navigation & Actions

### Action execution
- Actions execute in sequence; each can succeed or fail independently
- `execute_flow` continues past optional actions (e.g. two-step login's "Continue" button) rather than aborting
- Retry logic: up to 3 attempts with exponential backoff (`5.0 × 2^attempt` seconds)

### Checkpoint detection
- After navigation, if URL contains `/checkpoint/`, `/login`, or `/uas/login`, the bot halts and logs a warning
- Login redirect during `sync_single_conversation` triggers an inline re-login attempt before aborting

### Rate limiting
- A sliding window tracks action timestamps; if 20 actions occur within 60 seconds, execution pauses
- All page navigations and UI interactions go through the rate limiter

---

## CLI

- `sync` processes conversations in inbox order (most recent first)
- `sync` with `--limit N` stops after N conversations regardless of remaining inbox
- `sync` with `--since DATE` filters by `last_message_at >= DATE`
- Individual conversation failure does not abort the overall sync — remaining conversations continue
- Ctrl+C during sync displays partial results and exits cleanly
- `dump` output includes: connection name, direction indicator, timestamp, first ~100 chars of content
- `dump-tree` saves snapshot JSON to `.dm_bot_debug/snapshot_{timestamp}.json`
