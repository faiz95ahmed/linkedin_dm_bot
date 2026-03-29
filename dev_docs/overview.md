# LinkedIn DM Bot — Developer Overview

## Purpose

Automate LinkedIn messaging operations — sync conversations, extract messages and attachments — while avoiding detection through human-like behaviour patterns.

## Approach

- Uses mobile web UI (iPhone 5/SE viewport, 320×568, iOS 10 UA) instead of REST/GraphQL APIs
- Navigates via ARIA roles and accessible names, not CSS selectors
- Runs headful (not headless) to allow manual checkpoint intervention
- Stores state in SQLite for idempotent message processing
- macOS only (uses `osascript` for desktop notifications)

## Tech Stack

- **Language:** Python 3.13+, async/await throughout
- **Browser:** `playwright` — persistent context, mobile viewport
- **CLI:** `typer`
- **Data:** `pydantic`, `sqlite-utils`
- **Config:** `python-dotenv`
- **Link scraping:** `trafilatura`
- **Dev:** `pytest`, `pytest-asyncio`, `hypothesis`, `mypy`
- **Package manager:** `uv`

## Project Structure

```
dm_bot/
├── main.py           # CLI entry point
├── browser.py        # BrowserManager — Playwright setup, persistent context, mobile viewport
├── navigation.py     # NavigationEngine — page navigation, login flows, checkpoint detection
├── actions.py        # Action dataclass, ActionExecutor — accessibility-based element interaction
├── extraction.py     # InboxExtractor, ConnectionExtractor, MessageExtractor, SyncEngine
├── storage.py        # Pydantic models + repositories: Connection, Conversation, Message, Attachment
├── notifications.py  # NotificationService — macOS desktop alerts via osascript
├── utils.py          # AccessibilityDumper — builds/saves accessibility tree snapshots
└── config.py         # Constants, RateLimiter class, logging setup

tests/
├── test_actions.py
├── test_action_flows.py
├── test_browser.py
├── test_browser_integration.py
├── test_config.py
├── test_logging.py
├── test_navigation.py
├── test_notifications.py
├── test_rate_limiter.py
├── test_storage.py
└── test_sync_command.py

.persistence/         # git-ignored runtime state
├── browser_profile/  # Playwright persistent context (cookies, session)
├── dm_bot.db         # SQLite database
└── attachments/      # Downloaded files and scraped web pages
```

## Architecture

### Action System
- `Action` dataclass: `name`, `action_type`, `role`, `name_pattern`, `value`, handlers
- `ActionExecutor` executes actions with retry logic and exponential backoff (`5.0 × 2^attempt`)
- Action types: `wait_for`, `click`, `fill`, `check`
- Flows continue past optional actions (failure is not fatal)

### Accessibility Snapshot
- Uses `page.evaluate()` with custom JS `buildTree()` — NOT `page.accessibility.snapshot()` (removed in Playwright 1.40+)
- `IMPLICIT_ROLES` maps HTML tags to ARIA roles; `div` keeps role `"div"`
- Name = `aria-label || title || textContent[:2000]`

### DOM-Based Message Extraction
- **Layout A** (`li.msg-s-message-list__event`) — desktop/direct-nav LinkedIn
- **Layout B** (`li.member-message`) — SPA-routed mobile LinkedIn
- Conversation scrolled to top before extraction so all date separators are in the DOM
- Snapshot + DOM messages fetched in a single `page.evaluate()` call to avoid race conditions
- Timestamp resolution: single forward pass — date separators update `running_date`; un-timed messages accumulate until a timed message anchors the group, then back-filled at `t - 1s` per message

### Data Layer
- `DatabaseManager` handles SQLite connection and `CREATE TABLE IF NOT EXISTS` schema init
- Repository pattern: `ConnectionRepository`, `ConversationRepository`, `MessageRepository`, `AttachmentRepository`
- Deduplication key: `SHA256(f"{conversation_id}|{content}|{direction}")` — timestamp excluded intentionally

### Navigation & Error Handling
- `NavigationEngine` orchestrates action sequences, detects login/checkpoint redirects, applies rate limiting
- `CheckpointDetectedError` — non-retryable
- `ElementNotFoundError` — retry with exponential backoff (max 3 attempts)
- `NavigationTimeoutError` — retry once then abort
- `StorageError` — base for all DB errors

## Dev Commands

```bash
uv sync                                # install dependencies
uv run pytest                          # run all tests
uv run pytest --cov=dm_bot             # with coverage
uv run mypy dm_bot                     # type checking
uv run pytest tests/test_storage.py -v # single file
```
