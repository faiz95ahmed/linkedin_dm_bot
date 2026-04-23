"""CLI entry point for email sync."""

import base64
import fnmatch
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from dm_bot.config import setup_logging
from dm_bot.storage import DatabaseManager, SyncRepository
from email_sync.gws import gws_get_attachment, gws_list_messages, gws_get_message

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="email-sync",
    help="Fetch emails and manage blocklists",
    add_completion=False,
)
blocklist_app = typer.Typer(help="Manage named email blocklists")
app.add_typer(blocklist_app, name="blocklist")
blocklist_set_app = typer.Typer(help="Manage blocklist sets")
app.add_typer(blocklist_set_app, name="blocklist-set")


# =============================================================================
# Email Blocklist Repository (uses dm_bot.db)
# =============================================================================


class EmailBlocklistRepository:
    """Repository for named email blocklists and blocklist sets."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # -- Blocklists ----------------------------------------------------------

    def create_blocklist(self, name: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "INSERT INTO email_blocklist_name (name, created_at) VALUES (?, datetime('now'))",
            (name,),
        )
        conn.commit()

    def delete_blocklist(self, name: str) -> bool:
        conn = self._db.connect()
        cursor = conn.execute("DELETE FROM email_blocklist_name WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0

    def list_blocklists(self) -> list[str]:
        conn = self._db.connect()
        cursor = conn.execute("SELECT name FROM email_blocklist_name ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def add_pattern(self, blocklist_name: str, pattern: str) -> None:
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT id FROM email_blocklist_name WHERE name = ?", (blocklist_name,)
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Blocklist '{blocklist_name}' not found")
        conn.execute(
            "INSERT OR IGNORE INTO email_blocklist_item (blocklist_id, pattern, created_at) "
            "VALUES (?, ?, datetime('now'))",
            (row[0], pattern),
        )
        conn.commit()

    def remove_pattern(self, blocklist_name: str, pattern: str) -> bool:
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT id FROM email_blocklist_name WHERE name = ?", (blocklist_name,)
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Blocklist '{blocklist_name}' not found")
        cursor = conn.execute(
            "DELETE FROM email_blocklist_item WHERE blocklist_id = ? AND pattern = ?",
            (row[0], pattern),
        )
        conn.commit()
        return cursor.rowcount > 0

    def list_patterns(self, blocklist_name: str) -> list[str]:
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT i.pattern FROM email_blocklist_item i "
            "JOIN email_blocklist_name n ON i.blocklist_id = n.id "
            "WHERE n.name = ? ORDER BY i.pattern",
            (blocklist_name,),
        )
        return [row[0] for row in cursor.fetchall()]

    # -- Sets ----------------------------------------------------------------

    def create_set(self, name: str) -> None:
        conn = self._db.connect()
        conn.execute(
            "INSERT INTO email_blocklist_set (name, created_at) VALUES (?, datetime('now'))",
            (name,),
        )
        conn.commit()

    def delete_set(self, name: str) -> bool:
        conn = self._db.connect()
        cursor = conn.execute("DELETE FROM email_blocklist_set WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0

    def list_sets(self) -> list[str]:
        conn = self._db.connect()
        cursor = conn.execute("SELECT name FROM email_blocklist_set ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def add_to_set(self, set_name: str, blocklist_name: str) -> None:
        conn = self._db.connect()
        set_row = conn.execute(
            "SELECT id FROM email_blocklist_set WHERE name = ?", (set_name,)
        ).fetchone()
        if set_row is None:
            raise ValueError(f"Set '{set_name}' not found")
        bl_row = conn.execute(
            "SELECT id FROM email_blocklist_name WHERE name = ?", (blocklist_name,)
        ).fetchone()
        if bl_row is None:
            raise ValueError(f"Blocklist '{blocklist_name}' not found")
        conn.execute(
            "INSERT OR IGNORE INTO email_blocklist_set_member (set_id, blocklist_id) VALUES (?, ?)",
            (set_row[0], bl_row[0]),
        )
        conn.commit()

    def remove_from_set(self, set_name: str, blocklist_name: str) -> bool:
        conn = self._db.connect()
        set_row = conn.execute(
            "SELECT id FROM email_blocklist_set WHERE name = ?", (set_name,)
        ).fetchone()
        if set_row is None:
            raise ValueError(f"Set '{set_name}' not found")
        bl_row = conn.execute(
            "SELECT id FROM email_blocklist_name WHERE name = ?", (blocklist_name,)
        ).fetchone()
        if bl_row is None:
            raise ValueError(f"Blocklist '{blocklist_name}' not found")
        cursor = conn.execute(
            "DELETE FROM email_blocklist_set_member WHERE set_id = ? AND blocklist_id = ?",
            (set_row[0], bl_row[0]),
        )
        conn.commit()
        return cursor.rowcount > 0

    def show_set(self, set_name: str) -> list[str]:
        """Return blocklist names that are members of the given set."""
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT n.name FROM email_blocklist_name n "
            "JOIN email_blocklist_set_member m ON n.id = m.blocklist_id "
            "JOIN email_blocklist_set s ON s.id = m.set_id "
            "WHERE s.name = ? ORDER BY n.name",
            (set_name,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_patterns_for_set(self, set_name: str) -> list[str]:
        """Return the union of all patterns from all blocklists in a set."""
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT DISTINCT i.pattern FROM email_blocklist_item i "
            "JOIN email_blocklist_set_member m ON i.blocklist_id = m.blocklist_id "
            "JOIN email_blocklist_set s ON s.id = m.set_id "
            "WHERE s.name = ? ORDER BY i.pattern",
            (set_name,),
        )
        return [row[0] for row in cursor.fetchall()]


# =============================================================================
# Email parsing helpers
# =============================================================================

_EMAIL_RE = re.compile(r"<([^>]+)>")


def _extract_email(header_value: str) -> str:
    """Extract bare email from a From/To header like 'Name <addr>'."""
    m = _EMAIL_RE.search(header_value)
    return m.group(1).strip() if m else header_value.strip()


def _extract_emails(header_value: str) -> list[str]:
    """Extract list of emails from a To/Cc header (comma-separated)."""
    if not header_value:
        return []
    return [_extract_email(part) for part in header_value.split(",")]


def _get_header(headers: list[dict], name: str) -> str:
    """Get a header value by name (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def _get_text_body(payload: dict) -> str:
    """Extract text/plain body from a Gmail message payload."""
    # Simple single-part message
    mime = payload.get("mimeType", "")
    if mime == "text/plain" and "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Multipart — recurse into parts
    for part in payload.get("parts", []):
        result = _get_text_body(part)
        if result:
            return result

    return ""


def _get_attachments(payload: dict) -> list[dict]:
    """Extract attachment metadata (filename, mimeType, attachmentId) from payload."""
    attachments: list[dict] = []
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        if filename:
            entry: dict = {
                "filename": filename,
                "mimeType": part.get("mimeType", "application/octet-stream"),
            }
            att_id = part.get("body", {}).get("attachmentId")
            if att_id:
                entry["attachmentId"] = att_id
            attachments.append(entry)
        # Recurse for nested multipart
        attachments.extend(_get_attachments(part))
    return attachments


def _parse_message(raw: dict) -> dict:
    """Parse a raw Gmail API message into our schema."""
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])

    from_header = _get_header(headers, "From")
    return {
        "id": raw["id"],
        "threadId": raw.get("threadId", ""),
        "from": from_header,
        "from_email": _extract_email(from_header),
        "to": _extract_emails(_get_header(headers, "To")),
        "cc": _extract_emails(_get_header(headers, "Cc")),
        "subject": _get_header(headers, "Subject"),
        "date": _get_header(headers, "Date"),
        "snippet": raw.get("snippet", ""),
        "body": _get_text_body(payload),
        "attachments": _get_attachments(payload),
    }


# =============================================================================
# Last-sync command
# =============================================================================


@app.command("last-sync")
def last_sync() -> None:
    """Print the last email sync timestamp."""
    db = DatabaseManager()
    db.initialize_schema()
    ts = SyncRepository(db).get_last("email")
    if ts:
        typer.echo(ts)
    else:
        typer.echo("No email syncs recorded.")


# =============================================================================
# Fetch command
# =============================================================================


@app.command()
def fetch(
    since: Optional[str] = typer.Option(None, "--since", "-s", help="ISO datetime — fetch emails after this time (default: last completed sync)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output folder name (default: auto-generated)"),
    blocklist_set: str = typer.Option(..., "--blocklist-set", "-l", help="Blocklist set to use for filtering"),
    blocklist_extra: Optional[list[str]] = typer.Option(None, "--blocklist-extra", "-b", help="Extra blocklist patterns for this run"),
) -> None:
    """Fetch emails since a datetime, filter blocklisted senders, append JSON batches.

    Supports ongoing sync: if an ongoing sync exists, reuses its folder and start
    time. Otherwise creates a new ongoing sync. The sync stays ongoing until
    `collect` is run against the folder.
    """
    setup_logging(command="email-fetch")

    # Init DB and blocklist
    db = DatabaseManager()
    db.initialize_schema()
    sync_repo = SyncRepository(db)
    blocklist_repo = EmailBlocklistRepository(db)
    patterns = blocklist_repo.get_patterns_for_set(blocklist_set)
    if blocklist_extra:
        patterns.extend(blocklist_extra)

    logger.info("Blocklist set '%s': %d patterns", blocklist_set, len(patterns))

    # Resolve ongoing sync or create a new one
    ongoing = sync_repo.get_ongoing("email")
    if ongoing is not None:
        sync_id, sync_time, ongoing_dir = ongoing
        if output and output != ongoing_dir:
            typer.echo(
                f"Warning: ignoring --output '{output}' — "
                f"ongoing sync uses '{ongoing_dir}'",
                err=True,
            )
        if since:
            typer.echo(
                f"Warning: ignoring --since '{since}' — "
                f"ongoing sync started at {sync_time}",
                err=True,
            )
        out_name = ongoing_dir
        since_str = sync_time
        typer.echo(f"Resuming ongoing sync (folder={out_name}, since={since_str})")
    else:
        # Determine since
        if since:
            since_str = since
        else:
            last = sync_repo.get_last("email")
            if last is None:
                typer.echo(
                    "Error: no previous completed sync and --since not provided.",
                    err=True,
                )
                raise typer.Exit(1)
            since_str = last
        # Determine output dir name
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = output if output else f"email_{now_str}"
        # Create ongoing sync
        sync_id = sync_repo.start("email", out_name)
        typer.echo(f"Started new sync (folder={out_name}, since={since_str})")

    # Parse since datetime to epoch
    since_dt = since_str if isinstance(since_str, datetime) else datetime.fromisoformat(since_str)
    epoch = int(since_dt.timestamp())

    # Fetch message IDs
    query = f"after:{epoch}"
    msg_stubs = gws_list_messages(query)
    typer.echo(f"Found {len(msg_stubs)} message IDs")

    if not msg_stubs:
        typer.echo("No new messages found.")
        return

    # Fetch full messages
    messages: list[dict] = []
    blocked_count = 0
    for i, stub in enumerate(msg_stubs):
        if (i + 1) % 50 == 0:
            typer.echo(f"  Fetching message {i + 1}/{len(msg_stubs)}...")
        raw = gws_get_message(stub["id"])
        parsed = _parse_message(raw)

        # Check blocklist
        sender = parsed["from_email"]
        if any(fnmatch.fnmatch(sender.lower(), p.lower()) for p in patterns):
            blocked_count += 1
            continue
        messages.append(parsed)

    typer.echo(f"Fetched {len(messages)} messages ({blocked_count} blocked)")

    # Group by thread
    threads: dict[str, list[dict]] = defaultdict(list)
    for msg in messages:
        threads[msg["threadId"]].append(msg)

    # Sort messages within each thread by date
    for thread_msgs in threads.values():
        thread_msgs.sort(key=lambda m: m["date"])

    # Build output objects
    thread_list = [
        {"threadId": tid, "messages": msgs}
        for tid, msgs in threads.items()
    ]

    # Remove internal from_email field before writing
    for thread in thread_list:
        for msg in thread["messages"]:
            msg.pop("from_email", None)

    # Dedup against existing batch files
    out_dir = Path(f"/tmp/email-reader/{out_name}")
    out_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    existing_batches = sorted(out_dir.glob("[0-9]*.json"))
    for batch_file in existing_batches:
        if batch_file.name == "collected.json":
            continue
        try:
            data = json.loads(batch_file.read_text())
            for thread in data:
                tid = thread.get("threadId")
                if tid:
                    seen.add(tid)
        except (json.JSONDecodeError, KeyError):
            pass

    new_threads = [t for t in thread_list if t["threadId"] not in seen]
    dupes_skipped = len(thread_list) - len(new_threads)

    if not new_threads:
        typer.echo(
            f"No new threads ({dupes_skipped} already in folder, "
            f"{len(seen)} total threads in {len(existing_batches)} files)"
        )
        return

    # Append to batch files — fill last batch if under 10, then create new ones
    last_batch_idx = -1
    last_batch_data: list[dict] = []

    if existing_batches:
        last_batch_file = existing_batches[-1]
        last_batch_idx = int(last_batch_file.stem)
        try:
            last_batch_data = json.loads(last_batch_file.read_text())
        except (json.JSONDecodeError, KeyError):
            last_batch_data = []

    write_cursor = 0  # index into new_threads
    files_written = 0

    # Fill the last existing batch if it has room
    if last_batch_data and len(last_batch_data) < 10:
        room = 10 - len(last_batch_data)
        to_add = new_threads[:room]
        last_batch_data.extend(to_add)
        batch_path = out_dir / f"{last_batch_idx}.json"
        batch_path.write_text(json.dumps(last_batch_data, indent=2, ensure_ascii=False))
        write_cursor = len(to_add)
        files_written += 1

    # Write remaining threads in new batch files
    next_idx = last_batch_idx + 1 if last_batch_idx >= 0 else 0
    remaining = new_threads[write_cursor:]
    for i in range(0, len(remaining), 10):
        chunk = remaining[i : i + 10]
        batch_path = out_dir / f"{next_idx}.json"
        batch_path.write_text(json.dumps(chunk, indent=2, ensure_ascii=False))
        next_idx += 1
        files_written += 1

    total_files = len(list(out_dir.glob("[0-9]*.json")))
    typer.echo(
        f"Done: {len(new_threads)} new threads appended ({dupes_skipped} dupes skipped), "
        f"{blocked_count} blocked, {files_written} files written, "
        f"{len(seen) + len(new_threads)} total threads in {total_files} files"
    )


@app.command()
def pending() -> None:
    """Show status of the ongoing email sync."""
    db = DatabaseManager()
    db.initialize_schema()
    ongoing = SyncRepository(db).get_ongoing("email")
    if ongoing is None:
        typer.echo("No ongoing email sync.")
        return

    sync_id, sync_time, out_name = ongoing
    out_dir = Path(f"/tmp/email-reader/{out_name}")
    batch_files = sorted(out_dir.glob("[0-9]*.json")) if out_dir.is_dir() else []
    thread_count = 0
    for bf in batch_files:
        if bf.name == "collected.json":
            continue
        try:
            data = json.loads(bf.read_text())
            thread_count += len(data)
        except (json.JSONDecodeError, KeyError):
            pass

    typer.echo(f"Ongoing sync: {out_name}")
    typer.echo(f"  Folder: {out_dir}/")
    typer.echo(f"  Started: {sync_time}")
    typer.echo(f"  Batch files: {len(batch_files)} ({thread_count} threads)")


# =============================================================================
# Blocklist commands
# =============================================================================


@blocklist_app.command("create")
def blocklist_create(
    name: str = typer.Argument(..., help="Name for the new blocklist"),
) -> None:
    """Create a named blocklist."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    repo.create_blocklist(name)
    typer.echo(f"Created blocklist: {name}")


@blocklist_app.command("delete")
def blocklist_delete(
    name: str = typer.Argument(..., help="Blocklist to delete"),
) -> None:
    """Delete a blocklist and all its patterns."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    if repo.delete_blocklist(name):
        typer.echo(f"Deleted blocklist: {name}")
    else:
        typer.echo(f"Not found: {name}")


@blocklist_app.command("list")
def blocklist_list() -> None:
    """List all named blocklists."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    names = repo.list_blocklists()
    if not names:
        typer.echo("(empty)")
        return
    for n in names:
        typer.echo(n)


@blocklist_app.command("show")
def blocklist_show(
    name: str = typer.Argument(..., help="Blocklist to show"),
) -> None:
    """List patterns in a blocklist."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    patterns = repo.list_patterns(name)
    if not patterns:
        typer.echo("(empty)")
        return
    for p in patterns:
        typer.echo(p)


@blocklist_app.command("add")
def blocklist_add(
    name: str = typer.Argument(..., help="Blocklist to add patterns to"),
    patterns: list[str] = typer.Argument(..., help="Patterns to add"),
) -> None:
    """Add patterns to a named blocklist."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    for p in patterns:
        repo.add_pattern(name, p)
        typer.echo(f"Added: {p}")


@blocklist_app.command("remove")
def blocklist_remove(
    name: str = typer.Argument(..., help="Blocklist to remove patterns from"),
    patterns: list[str] = typer.Argument(..., help="Patterns to remove"),
) -> None:
    """Remove patterns from a named blocklist."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    for p in patterns:
        if repo.remove_pattern(name, p):
            typer.echo(f"Removed: {p}")
        else:
            typer.echo(f"Not found: {p}")


# =============================================================================
# Blocklist set commands
# =============================================================================


@blocklist_set_app.command("create")
def set_create(
    name: str = typer.Argument(..., help="Name for the new set"),
) -> None:
    """Create a blocklist set."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    repo.create_set(name)
    typer.echo(f"Created set: {name}")


@blocklist_set_app.command("delete")
def set_delete(
    name: str = typer.Argument(..., help="Set to delete"),
) -> None:
    """Delete a blocklist set."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    if repo.delete_set(name):
        typer.echo(f"Deleted set: {name}")
    else:
        typer.echo(f"Not found: {name}")


@blocklist_set_app.command("list")
def set_list() -> None:
    """List all blocklist sets."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    names = repo.list_sets()
    if not names:
        typer.echo("(empty)")
        return
    for n in names:
        typer.echo(n)


@blocklist_set_app.command("show")
def set_show(
    name: str = typer.Argument(..., help="Set to show"),
) -> None:
    """Show blocklists in a set."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    members = repo.show_set(name)
    if not members:
        typer.echo("(empty)")
        return
    for m in members:
        typer.echo(m)


@blocklist_set_app.command("add")
def set_add(
    name: str = typer.Argument(..., help="Set to add blocklists to"),
    blocklists: list[str] = typer.Argument(..., help="Blocklist names to add"),
) -> None:
    """Add blocklists to a set."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    for bl in blocklists:
        repo.add_to_set(name, bl)
        typer.echo(f"Added {bl} to set {name}")


@blocklist_set_app.command("remove")
def set_remove(
    name: str = typer.Argument(..., help="Set to remove blocklists from"),
    blocklists: list[str] = typer.Argument(..., help="Blocklist names to remove"),
) -> None:
    """Remove blocklists from a set."""
    db = DatabaseManager()
    db.initialize_schema()
    repo = EmailBlocklistRepository(db)
    for bl in blocklists:
        if repo.remove_from_set(name, bl):
            typer.echo(f"Removed {bl} from set {name}")
        else:
            typer.echo(f"Not found: {bl} in set {name}")


@app.command()
def collect(
    folder: str = typer.Option(..., "--folder", "-f", help="Folder name under /tmp/email-reader/"),
    thread_ids: Optional[list[str]] = typer.Argument(None, help="Thread IDs to collect"),
    none: bool = typer.Option(False, "--none", help="Complete sync with no relevant threads"),
) -> None:
    """Collect specific threads from batch files into a single JSON, downloading attachments."""
    if not thread_ids and not none:
        typer.echo("Error: provide THREAD_IDS or --none to complete with no threads", err=True)
        raise typer.Exit(1)
    src_dir = Path(f"/tmp/email-reader/{folder}")
    if not src_dir.is_dir():
        typer.echo(f"Error: {src_dir} does not exist", err=True)
        raise typer.Exit(1)

    wanted = set(thread_ids or [])
    found: list[dict] = []

    for json_file in sorted(src_dir.glob("*.json")):
        data = json.loads(json_file.read_text())
        for thread in data:
            if thread.get("threadId") in wanted:
                found.append(thread)
                wanted.discard(thread["threadId"])
        if not wanted:
            break

    if wanted:
        typer.echo(f"Warning: {len(wanted)} thread(s) not found: {', '.join(wanted)}", err=True)

    # Download attachments
    att_dir = src_dir / "attachments"
    att_dir.mkdir(exist_ok=True)
    att_count = 0
    for thread in found:
        for msg in thread.get("messages", []):
            msg_id = msg.get("id", "")
            for att in msg.get("attachments", []):
                attachment_id = att.get("attachmentId")
                if not attachment_id:
                    continue
                filename = att.get("filename", "attachment")
                safe_name = f"{msg_id}_{filename}"
                local_path = att_dir / safe_name
                if local_path.exists():
                    att["localPath"] = str(local_path)
                    att_count += 1
                    continue
                try:
                    data = gws_get_attachment(msg_id, attachment_id)
                    local_path.write_bytes(data)
                    att["localPath"] = str(local_path)
                    att_count += 1
                    typer.echo(f"  Downloaded: {safe_name}")
                except Exception as e:
                    typer.echo(f"  Failed to download {safe_name}: {e}", err=True)
                # Remove internal attachmentId from output
                att.pop("attachmentId", None)

    out_path = src_dir / "collected.json"
    out_path.write_text(json.dumps(found, indent=2, ensure_ascii=False))
    typer.echo(f"Wrote {len(found)} threads to {out_path} ({att_count} attachments downloaded)")

    # Complete ongoing sync if one matches this folder
    db = DatabaseManager()
    db.initialize_schema()
    sync_repo = SyncRepository(db)
    ongoing = sync_repo.get_ongoing("email")
    if ongoing is not None and ongoing[2] == folder:
        sync_repo.complete(ongoing[0])
        typer.echo(f"Marked sync '{folder}' as completed.")


@app.command("download-attachments")
def download_attachments(
    message_id: str = typer.Argument(..., help="Gmail message ID"),
    output_dir: Path = typer.Option(
        Path("/tmp") / Path.cwd().name,
        "-o",
        "--output",
        help="Directory to save attachments (default: /tmp/<cwd_name>/)",
    ),
) -> None:
    """Download all attachments from a Gmail message by ID."""
    msg = gws_get_message(message_id)
    payload = msg.get("payload", {})
    attachments = _get_attachments(payload)

    if not attachments:
        typer.echo("No attachments found.")
        raise typer.Exit()

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for att in attachments:
        attachment_id = att.get("attachmentId")
        if not attachment_id:
            continue
        filename = att.get("filename", "attachment")
        local_path = output_dir / filename
        if local_path.exists():
            typer.echo(f"  Already exists: {filename}")
            downloaded += 1
            continue
        try:
            data = gws_get_attachment(message_id, attachment_id)
            local_path.write_bytes(data)
            typer.echo(f"  Downloaded: {filename} ({len(data)} bytes)")
            downloaded += 1
        except Exception as e:
            typer.echo(f"  Failed: {filename}: {e}", err=True)

    typer.echo(f"Done: {downloaded}/{len(attachments)} attachments saved to {output_dir}")


def main() -> None:
    app()
