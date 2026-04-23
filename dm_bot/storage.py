"""Data storage models and exceptions for the LinkedIn DM Bot.

This module provides Pydantic models for Connection, Conversation, and Message entities,
along with custom exceptions for storage layer errors. It also includes the
DatabaseManager class for managing SQLite database connections and schema.
"""

import hashlib
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================


class StorageError(Exception):
    """Base exception for storage layer errors."""

    pass


class ConnectionNotFoundError(StorageError):
    """Raised when a required Connection doesn't exist."""

    pass


class ConversationNotFoundError(StorageError):
    """Raised when a required Conversation doesn't exist."""

    pass


# =============================================================================
# Data Models
# =============================================================================


class Connection(BaseModel):
    """Represents a LinkedIn user we've interacted with.

    Attributes:
        id: Database primary key, None for new records
        linkedin_slug: Unique identifier from LinkedIn profile URL
        display_name: User's display name on LinkedIn
        profile_url: Full URL to the user's LinkedIn profile
        first_seen_at: Timestamp when this connection was first discovered
        updated_at: Timestamp of the last update to this record
    """

    linkedin_slug: str
    display_name: str
    profile_url: str
    first_seen_at: datetime
    updated_at: datetime
    id: int | None = None


class Conversation(BaseModel):
    """Represents a message thread with a connection.

    Attributes:
        id: Database primary key, None for new records
        connection_id: Foreign key to the associated Connection
        thread_url: URL to the conversation thread on LinkedIn
        last_message_at: Timestamp of the most recent message
        last_synced_at: Timestamp of the last sync operation
        created_at: Timestamp when this conversation was created
    """

    connection_id: int
    created_at: datetime
    id: int | None = None
    thread_url: str | None = None
    last_message_at: datetime | None = None
    last_synced_at: datetime | None = None
    triaged_at: datetime | None = None


class Message(BaseModel):
    """Represents a single message in a conversation.

    Attributes:
        id: Database primary key, None for new records
        conversation_id: Foreign key to the associated Conversation
        linkedin_msg_id: LinkedIn's message identifier (may not be available)
        sender_id: Foreign key to Connection if inbound, None if outbound
        content: The message text content
        timestamp: When the message was sent
        direction: 'inbound' for received messages, 'outbound' for sent messages
        synced_at: When this message was synced to the database
        dedup_key: Deduplication key generated on storage
    """

    conversation_id: int
    content: str
    timestamp: datetime
    direction: Literal["inbound", "outbound"]
    synced_at: datetime
    id: int | None = None
    linkedin_msg_id: str | None = None
    sender_id: int | None = None
    dedup_key: str | None = None


class Attachment(BaseModel):
    """Represents a file attachment linked to a message.

    Attributes:
        id: Database primary key, None for new records
        message_id: Foreign key to the associated Message
        attachment_path: Path to the file on disk (unique; filename mangled for uniqueness)
        original_filename: Original filename before mangling
        content_type: MIME type if known
        file_size: File size in bytes if known
    """

    message_id: int
    attachment_path: str
    original_filename: str
    id: int | None = None
    content_type: str | None = None
    file_size: int | None = None


# =============================================================================
# Database Configuration
# =============================================================================

DEFAULT_DB_PATH: Path = Path(__file__).parent.parent / ".persistence" / "dm_bot.db"
DB_PATH: Path = Path(os.getenv("DM_BOT_DB_PATH", str(DEFAULT_DB_PATH)))


# Register datetime adapters and converters for SQLite
def _adapt_datetime(dt: datetime) -> str:
    """Convert datetime to ISO format string for SQLite storage."""
    return dt.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    """Convert ISO format string from SQLite to datetime."""
    return datetime.fromisoformat(val.decode())


# Register the adapters and converters
sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("DATETIME", _convert_datetime)


# =============================================================================
# Database Manager
# =============================================================================


class DatabaseManager:
    """Manages SQLite database connection and schema.

    This class handles database connection lifecycle and schema initialization.
    It supports configurable database paths via the DM_BOT_DB_PATH environment
    variable with a fallback to .persistence/dm_bot.db inside the repo.

    Attributes:
        db_path: Path to the SQLite database file
        _connection: The active SQLite connection, or None if not connected
    """

    # SQL schema for creating tables
    _SCHEMA_SQL = """
        -- Connection table: stores LinkedIn users we've interacted with
        CREATE TABLE IF NOT EXISTS connection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            linkedin_slug TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            profile_url TEXT NOT NULL,
            first_seen_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );

        -- Conversation table: stores message threads with connections
        CREATE TABLE IF NOT EXISTS conversation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id INTEGER UNIQUE NOT NULL,
            thread_url TEXT,
            last_message_at DATETIME,
            last_synced_at DATETIME,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (connection_id) REFERENCES connection(id)
        );

        -- Message table: stores individual messages in conversations
        CREATE TABLE IF NOT EXISTS message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            linkedin_msg_id TEXT,
            sender_id INTEGER,
            content TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
            synced_at DATETIME NOT NULL,
            dedup_key TEXT UNIQUE NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversation(id),
            FOREIGN KEY (sender_id) REFERENCES connection(id)
        );

        -- Index for efficient deduplication key lookups
        CREATE INDEX IF NOT EXISTS idx_message_dedup_key ON message(dedup_key);

        -- Index for querying messages by conversation and timestamp
        CREATE INDEX IF NOT EXISTS idx_message_conversation_timestamp 
            ON message(conversation_id, timestamp);

        -- Index for sync queries (conversations needing sync)
        CREATE INDEX IF NOT EXISTS idx_conversation_sync
            ON conversation(last_message_at, last_synced_at);

        -- Attachment table: files linked to messages
        CREATE TABLE IF NOT EXISTS attachment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            attachment_path TEXT UNIQUE NOT NULL,
            original_filename TEXT NOT NULL,
            content_type TEXT,
            file_size INTEGER,
            FOREIGN KEY (message_id) REFERENCES message(id)
        );

        -- Index for fetching attachments by message
        CREATE INDEX IF NOT EXISTS idx_attachment_message_id ON attachment(message_id);

        -- Log table: stores structured log records for CLI runs
        CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            command TEXT NOT NULL,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            level_no INTEGER NOT NULL,
            logger TEXT NOT NULL,
            module TEXT NOT NULL,
            func TEXT NOT NULL,
            lineno INTEGER NOT NULL,
            message TEXT NOT NULL,
            exc_text TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_log_run_id ON log(run_id);
        CREATE INDEX IF NOT EXISTS idx_log_ts ON log(ts);
        CREATE INDEX IF NOT EXISTS idx_log_level_no ON log(level_no);
        CREATE INDEX IF NOT EXISTS idx_log_logger ON log(logger);
        CREATE INDEX IF NOT EXISTS idx_log_command ON log(command);

        -- Drop legacy flat blocklist table
        DROP TABLE IF EXISTS email_blocklist;

        -- Named blocklists
        CREATE TABLE IF NOT EXISTS email_blocklist_name (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at DATETIME NOT NULL
        );

        -- Blocklist items (patterns belonging to a named blocklist)
        CREATE TABLE IF NOT EXISTS email_blocklist_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blocklist_id INTEGER NOT NULL,
            pattern TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (blocklist_id) REFERENCES email_blocklist_name(id) ON DELETE CASCADE,
            UNIQUE(blocklist_id, pattern)
        );

        -- Blocklist sets (named groups of blocklists)
        CREATE TABLE IF NOT EXISTS email_blocklist_set (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at DATETIME NOT NULL
        );

        -- Set membership (which blocklists belong to which sets)
        CREATE TABLE IF NOT EXISTS email_blocklist_set_member (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER NOT NULL,
            blocklist_id INTEGER NOT NULL,
            FOREIGN KEY (set_id) REFERENCES email_blocklist_set(id) ON DELETE CASCADE,
            FOREIGN KEY (blocklist_id) REFERENCES email_blocklist_name(id) ON DELETE CASCADE,
            UNIQUE(set_id, blocklist_id)
        );

        -- Sync table: tracks when email and LinkedIn syncs were performed
        CREATE TABLE IF NOT EXISTS sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_type TEXT NOT NULL CHECK (sync_type IN ('email', 'linkedin')),
            sync_time DATETIME NOT NULL,
            completed_at DATETIME,
            output_dir TEXT
        );
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize DatabaseManager with optional custom path.

        Args:
            db_path: Path to the SQLite database file. If None, uses the
                    DM_BOT_DB_PATH environment variable or defaults to
                    .persistence/dm_bot.db inside the repo
        """
        if db_path is not None:
            self.db_path = db_path
        else:
            self.db_path = DB_PATH

        self._connection: sqlite3.Connection | None = None
        logger.debug(f"DatabaseManager initialized with path: {self.db_path}")

    def connect(self) -> sqlite3.Connection:
        """Get or create database connection.

        Creates parent directories if they don't exist. Returns the existing
        connection if already connected.

        Returns:
            Active SQLite connection

        Raises:
            StorageError: If the database file cannot be created or accessed
        """
        if self._connection is not None:
            return self._connection

        try:
            # Create parent directories if they don't exist
            # Skip for in-memory databases
            if str(self.db_path) != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

            self._connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            # Enable foreign key constraints
            self._connection.execute("PRAGMA foreign_keys = ON")
            logger.info(f"Connected to database: {self.db_path}")
            return self._connection

        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise StorageError(f"Failed to connect to database: {e}") from e
        except OSError as e:
            logger.error(f"Failed to create database directory: {e}")
            raise StorageError(f"Failed to create database directory: {e}") from e

    def initialize_schema(self) -> None:
        """Create tables and indexes if they don't exist.

        This method is idempotent - it can be called multiple times without
        modifying existing data. Uses IF NOT EXISTS clauses for all DDL.

        Raises:
            StorageError: If schema initialization fails
        """
        conn = self.connect()
        try:
            conn.executescript(self._SCHEMA_SQL)
            conn.commit()
            # Migrations — idempotent ALTER TABLE additions
            for col, typedef in [
                ("completed_at", "DATETIME"),
                ("output_dir", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE sync ADD COLUMN {col} {typedef}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # column already exists
            # Add triaged_at to conversation table
            try:
                conn.execute("ALTER TABLE conversation ADD COLUMN triaged_at DATETIME")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
            # Backfill legacy rows: treat them as completed
            conn.execute(
                "UPDATE sync SET completed_at = sync_time "
                "WHERE completed_at IS NULL AND output_dir IS NULL"
            )
            conn.commit()
            logger.info("Database schema initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise StorageError(f"Failed to initialize schema: {e}") from e

    def close(self) -> None:
        """Close database connection.

        Safe to call multiple times - does nothing if already closed.
        """
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")


# =============================================================================
# Connection Repository
# =============================================================================


class ConnectionRepository:
    """Repository for Connection entities.

    Handles CRUD operations for Connection records with support for
    upsert behavior (insert or update based on linkedin_slug).
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Initialize with database manager.

        Args:
            db: DatabaseManager instance for database operations
        """
        self._db = db

    def upsert(self, connection: Connection) -> Connection:
        """Insert or update a connection, returns the stored connection.

        Uses INSERT OR REPLACE to handle upsert behavior. If a connection
        with the same linkedin_slug exists, it will be updated.

        Args:
            connection: Connection object to store

        Returns:
            Connection object with populated id field

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO connection 
                    (linkedin_slug, display_name, profile_url, first_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    connection.linkedin_slug,
                    connection.display_name,
                    connection.profile_url,
                    connection.first_seen_at,
                    connection.updated_at,
                ),
            )
            conn.commit()

            # Return connection with populated id
            return Connection(
                id=cursor.lastrowid,
                linkedin_slug=connection.linkedin_slug,
                display_name=connection.display_name,
                profile_url=connection.profile_url,
                first_seen_at=connection.first_seen_at,
                updated_at=connection.updated_at,
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to upsert connection: {e}")
            raise StorageError(f"Failed to upsert connection: {e}") from e

    def update(self, connection: Connection) -> None:
        """Update an existing connection by id.

        Uses UPDATE WHERE id=? to preserve the primary key, avoiding
        foreign key breakage that INSERT OR REPLACE would cause.

        Args:
            connection: Connection with populated id to update

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            conn.execute(
                """
                UPDATE connection
                SET display_name=?, profile_url=?, updated_at=?
                WHERE id=?
                """,
                (
                    connection.display_name,
                    connection.profile_url,
                    connection.updated_at,
                    connection.id,
                ),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to update connection: {e}")
            raise StorageError(f"Failed to update connection: {e}") from e

    def get_by_slug(self, linkedin_slug: str) -> Connection | None:
        """Find connection by LinkedIn slug.

        Args:
            linkedin_slug: The unique LinkedIn profile slug to search for

        Returns:
            Connection object if found, None otherwise

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, linkedin_slug, display_name, profile_url, 
                       first_seen_at, updated_at
                FROM connection
                WHERE linkedin_slug = ?
                """,
                (linkedin_slug,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return Connection(
                id=row[0],
                linkedin_slug=row[1],
                display_name=row[2],
                profile_url=row[3],
                first_seen_at=row[4],
                updated_at=row[5],
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to get connection by slug: {e}")
            raise StorageError(f"Failed to get connection by slug: {e}") from e

    def list_all(self) -> list[Connection]:
        """List all connections ordered by updated_at desc.

        Returns:
            List of all Connection objects, ordered by updated_at descending

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, linkedin_slug, display_name, profile_url, 
                       first_seen_at, updated_at
                FROM connection
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()

            return [
                Connection(
                    id=row[0],
                    linkedin_slug=row[1],
                    display_name=row[2],
                    profile_url=row[3],
                    first_seen_at=row[4],
                    updated_at=row[5],
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to list connections: {e}")
            raise StorageError(f"Failed to list connections: {e}") from e


# =============================================================================
# Conversation Repository
# =============================================================================


class ConversationRepository:
    """Repository for Conversation entities.

    Handles CRUD operations for Conversation records with support for
    upsert behavior (insert or update based on connection_id) and
    sync status queries.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Initialize with database manager.

        Args:
            db: DatabaseManager instance for database operations
        """
        self._db = db

    def upsert(self, conversation: Conversation) -> Conversation:
        """Insert or update a conversation, returns the stored conversation.

        Uses INSERT OR REPLACE to handle upsert behavior. If a conversation
        with the same connection_id exists, it will be updated.

        Args:
            conversation: Conversation object to store

        Returns:
            Conversation object with populated id field

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO conversation
                    (connection_id, thread_url, last_message_at, last_synced_at, created_at, triaged_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id) DO UPDATE SET
                    thread_url = excluded.thread_url,
                    last_message_at = excluded.last_message_at,
                    last_synced_at = excluded.last_synced_at,
                    triaged_at = COALESCE(excluded.triaged_at, conversation.triaged_at)
                """,
                (
                    conversation.connection_id,
                    conversation.thread_url,
                    conversation.last_message_at,
                    conversation.last_synced_at,
                    conversation.created_at,
                    conversation.triaged_at,
                ),
            )
            conn.commit()

            # Fetch the actual row to get the correct id and triaged_at
            row = conn.execute(
                "SELECT id, triaged_at FROM conversation WHERE connection_id = ?",
                (conversation.connection_id,),
            ).fetchone()

            return Conversation(
                id=row[0],
                connection_id=conversation.connection_id,
                thread_url=conversation.thread_url,
                last_message_at=conversation.last_message_at,
                last_synced_at=conversation.last_synced_at,
                created_at=conversation.created_at,
                triaged_at=row[1],
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to upsert conversation: {e}")
            raise StorageError(f"Failed to upsert conversation: {e}") from e

    def get_by_connection_id(self, connection_id: int) -> Conversation | None:
        """Find conversation by connection ID.

        Args:
            connection_id: The connection ID to search for

        Returns:
            Conversation object if found, None otherwise

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, connection_id, thread_url, last_message_at,
                       last_synced_at, created_at, triaged_at
                FROM conversation
                WHERE connection_id = ?
                """,
                (connection_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return Conversation(
                id=row[0],
                connection_id=row[1],
                thread_url=row[2],
                last_message_at=row[3],
                last_synced_at=row[4],
                created_at=row[5],
                triaged_at=row[6],
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to get conversation by connection_id: {e}")
            raise StorageError(
                f"Failed to get conversation by connection_id: {e}"
            ) from e

    def get_by_id(self, conversation_id: int) -> "Conversation | None":
        """Find conversation by primary key."""
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, connection_id, thread_url, last_message_at,
                       last_synced_at, created_at, triaged_at
                FROM conversation WHERE id = ?
                """,
                (conversation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Conversation(
                id=row[0], connection_id=row[1], thread_url=row[2],
                last_message_at=row[3], last_synced_at=row[4], created_at=row[5],
                triaged_at=row[6],
            )
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get conversation by id: {e}") from e

    def get_by_thread_url(self, thread_url: str) -> "Conversation | None":
        """Find conversation by thread URL (ignoring query parameters).

        Uses a prefix match on the base URL (before '?') so that trk= params
        don't cause misses.

        Args:
            thread_url: Full or base thread URL to search for

        Returns:
            Conversation object if found, None otherwise
        """
        base_url = thread_url.split("?")[0]
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, connection_id, thread_url, last_message_at,
                       last_synced_at, created_at, triaged_at
                FROM conversation
                WHERE thread_url LIKE ?
                """,
                (base_url + "%",),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Conversation(
                id=row[0],
                connection_id=row[1],
                thread_url=row[2],
                last_message_at=row[3],
                last_synced_at=row[4],
                created_at=row[5],
                triaged_at=row[6],
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to get conversation by thread_url: {e}")
            raise StorageError(f"Failed to get conversation by thread_url: {e}") from e

    def update_connection_id(self, conversation_id: int, connection_id: int) -> None:
        """Reassign a conversation to a different connection."""
        conn = self._db.connect()
        try:
            conn.execute(
                "UPDATE conversation SET connection_id = ? WHERE id = ?",
                (connection_id, conversation_id),
            )
            conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to update conversation connection_id: {e}") from e

    def get_needing_sync(
        self, since: datetime | None = None, limit: int = 50
    ) -> list[Conversation]:
        """Get conversations where last_message_at > last_synced_at.

        Returns conversations that have new messages since the last sync.
        Supports filtering by last_message_at with a since parameter and
        limiting the number of results.

        Args:
            since: Optional datetime to filter conversations with
                   last_message_at >= since
            limit: Maximum number of results to return (default 50)

        Returns:
            List of Conversation objects needing sync

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            # Build query based on parameters
            if since is not None:
                cursor = conn.execute(
                    """
                    SELECT id, connection_id, thread_url, last_message_at,
                           last_synced_at, created_at, triaged_at
                    FROM conversation
                    WHERE last_message_at IS NOT NULL
                      AND (last_synced_at IS NULL OR last_message_at > last_synced_at)
                      AND last_message_at >= ?
                    ORDER BY last_message_at DESC
                    LIMIT ?
                    """,
                    (since, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, connection_id, thread_url, last_message_at,
                           last_synced_at, created_at, triaged_at
                    FROM conversation
                    WHERE last_message_at IS NOT NULL
                      AND (last_synced_at IS NULL OR last_message_at > last_synced_at)
                    ORDER BY last_message_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            rows = cursor.fetchall()

            return [
                Conversation(
                    id=row[0],
                    connection_id=row[1],
                    thread_url=row[2],
                    last_message_at=row[3],
                    last_synced_at=row[4],
                    created_at=row[5],
                    triaged_at=row[6],
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get conversations needing sync: {e}")
            raise StorageError(
                f"Failed to get conversations needing sync: {e}"
            ) from e

    def update_sync_timestamp(
        self, conversation_id: int, synced_at: datetime
    ) -> None:
        """Update the last_synced_at timestamp.

        Args:
            conversation_id: ID of the conversation to update
            synced_at: The new sync timestamp

        Raises:
            ConversationNotFoundError: If the conversation doesn't exist
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE conversation
                SET last_synced_at = ?
                WHERE id = ?
                """,
                (synced_at, conversation_id),
            )
            conn.commit()

            if cursor.rowcount == 0:
                raise ConversationNotFoundError(
                    f"Conversation with id {conversation_id} not found"
                )
        except ConversationNotFoundError:
            raise
        except sqlite3.Error as e:
            logger.error(f"Failed to update sync timestamp: {e}")
            raise StorageError(f"Failed to update sync timestamp: {e}") from e

    def update_last_message_at(
        self, conversation_id: int, last_message_at: datetime
    ) -> None:
        """Update the last_message_at timestamp from actual stored messages.

        Args:
            conversation_id: ID of the conversation to update
            last_message_at: Timestamp of the most recent message

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            conn.execute(
                "UPDATE conversation SET last_message_at = ? WHERE id = ?",
                (last_message_at, conversation_id),
            )
            conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to update last_message_at: {e}") from e

    def triage(self, conversation_id: int) -> None:
        """Mark a conversation as triaged."""
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                "UPDATE conversation SET triaged_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise ConversationNotFoundError(
                    f"Conversation with id {conversation_id} not found"
                )
        except ConversationNotFoundError:
            raise
        except sqlite3.Error as e:
            raise StorageError(f"Failed to triage conversation: {e}") from e

    def triage_many(self, conversation_ids: list[int]) -> int:
        """Bulk-triage conversations. Returns count updated."""
        conn = self._db.connect()
        try:
            placeholders = ",".join("?" for _ in conversation_ids)
            cursor = conn.execute(
                f"UPDATE conversation SET triaged_at = datetime('now') WHERE id IN ({placeholders})",
                conversation_ids,
            )
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            raise StorageError(f"Failed to triage conversations: {e}") from e

    def triage_all_untriaged(self) -> int:
        """Triage all conversations that are untriaged or have new messages. Returns count."""
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE conversation SET triaged_at = datetime('now')
                WHERE triaged_at IS NULL
                   OR replace(last_message_at, 'T', ' ') > replace(triaged_at, 'T', ' ')
                """,
            )
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as e:
            raise StorageError(f"Failed to triage all conversations: {e}") from e


# =============================================================================
# Message Repository
# =============================================================================


class MessageRepository:
    """Repository for Message entities.

    Handles CRUD operations for Message records with support for
    deduplication based on conversation_id, timestamp, and content hash.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Initialize with database manager.

        Args:
            db: DatabaseManager instance for database operations
        """
        self._db = db

    @staticmethod
    def generate_dedup_key(
        conversation_id: int, timestamp: datetime | None, content: str,
        direction: str = ""
    ) -> str:
        """Generate deduplication key from message attributes.

        Uses conversation_id + content + direction (not timestamp) so that
        re-syncing with unreliable timestamps does not create duplicate records.

        Args:
            conversation_id: ID of the conversation this message belongs to
            timestamp: Unused (kept for API compatibility)
            content: The message text content
            direction: "inbound" or "outbound"

        Returns:
            Hexadecimal string of the SHA256 hash
        """
        key_data = f"{conversation_id}|{content}|{direction}"
        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()

    def store(self, message: Message) -> Message:
        """Store message with deduplication, returns stored or existing message.

        If a message with the same deduplication key already exists, returns
        the existing message without modification. Otherwise, inserts the new
        message and returns it with populated id and dedup_key fields.

        Args:
            message: Message object to store

        Returns:
            Message object with populated id and dedup_key fields

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()

        # Generate dedup key if not already set
        dedup_key = message.dedup_key or self.generate_dedup_key(
            message.conversation_id, message.timestamp, message.content
        )

        try:
            # First, check if a message with this dedup_key already exists
            cursor = conn.execute(
                """
                SELECT id, conversation_id, linkedin_msg_id, sender_id, content,
                       timestamp, direction, synced_at, dedup_key
                FROM message
                WHERE dedup_key = ?
                """,
                (dedup_key,),
            )
            existing_row = cursor.fetchone()

            if existing_row is not None:
                # Return existing message
                return Message(
                    id=existing_row[0],
                    conversation_id=existing_row[1],
                    linkedin_msg_id=existing_row[2],
                    sender_id=existing_row[3],
                    content=existing_row[4],
                    timestamp=existing_row[5],
                    direction=existing_row[6],
                    synced_at=existing_row[7],
                    dedup_key=existing_row[8],
                )

            # Insert new message
            cursor = conn.execute(
                """
                INSERT INTO message 
                    (conversation_id, linkedin_msg_id, sender_id, content,
                     timestamp, direction, synced_at, dedup_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.conversation_id,
                    message.linkedin_msg_id,
                    message.sender_id,
                    message.content,
                    message.timestamp,
                    message.direction,
                    message.synced_at,
                    dedup_key,
                ),
            )
            conn.commit()

            # Return message with populated id and dedup_key
            return Message(
                id=cursor.lastrowid,
                conversation_id=message.conversation_id,
                linkedin_msg_id=message.linkedin_msg_id,
                sender_id=message.sender_id,
                content=message.content,
                timestamp=message.timestamp,
                direction=message.direction,
                synced_at=message.synced_at,
                dedup_key=dedup_key,
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to store message: {e}")
            raise StorageError(f"Failed to store message: {e}") from e

    def get_by_conversation(self, conversation_id: int) -> list[Message]:
        """Get all messages for a conversation ordered by timestamp asc.

        Args:
            conversation_id: ID of the conversation to get messages for

        Returns:
            List of Message objects ordered by timestamp ascending

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, conversation_id, linkedin_msg_id, sender_id, content,
                       timestamp, direction, synced_at, dedup_key
                FROM message
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
                """,
                (conversation_id,),
            )
            rows = cursor.fetchall()

            return [
                Message(
                    id=row[0],
                    conversation_id=row[1],
                    linkedin_msg_id=row[2],
                    sender_id=row[3],
                    content=row[4],
                    timestamp=row[5],
                    direction=row[6],
                    synced_at=row[7],
                    dedup_key=row[8],
                )
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get messages by conversation: {e}")
            raise StorageError(f"Failed to get messages by conversation: {e}") from e


# =============================================================================
# Attachment Repository
# =============================================================================


class AttachmentRepository:
    """Repository for Attachment entities.

    Handles storing and retrieving file attachments linked to messages.
    Filenames are mangled to `{message_id}_{original_filename}` before storage
    to guarantee uniqueness on disk.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @staticmethod
    def make_filename(message_id: int, original_filename: str) -> str:
        """Return a unique filename for disk storage.

        Args:
            message_id: ID of the message this attachment belongs to
            original_filename: Original filename from LinkedIn

        Returns:
            Mangled filename in the form ``{message_id}_{original_filename}``
        """
        return f"{message_id}_{original_filename}"

    def store(self, attachment: Attachment) -> Attachment:
        """Insert an attachment record, skipping if attachment_path already exists.

        Args:
            attachment: Attachment object to store (id must be None)

        Returns:
            Attachment with populated id field, or the existing record if the
            attachment_path is already present.

        Raises:
            StorageError: If the database operation fails
        """
        conn = self._db.connect()
        try:
            # Check for existing record with same path
            cursor = conn.execute(
                "SELECT id, message_id, attachment_path, original_filename, "
                "content_type, file_size FROM attachment WHERE attachment_path = ?",
                (attachment.attachment_path,),
            )
            row = cursor.fetchone()
            if row is not None:
                return Attachment(
                    id=row[0], message_id=row[1], attachment_path=row[2],
                    original_filename=row[3], content_type=row[4], file_size=row[5],
                )

            cursor = conn.execute(
                """
                INSERT INTO attachment (message_id, attachment_path, original_filename,
                                        content_type, file_size)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    attachment.message_id,
                    attachment.attachment_path,
                    attachment.original_filename,
                    attachment.content_type,
                    attachment.file_size,
                ),
            )
            conn.commit()
            return Attachment(
                id=cursor.lastrowid,
                message_id=attachment.message_id,
                attachment_path=attachment.attachment_path,
                original_filename=attachment.original_filename,
                content_type=attachment.content_type,
                file_size=attachment.file_size,
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to store attachment: {e}")
            raise StorageError(f"Failed to store attachment: {e}") from e

    def get_by_message(self, message_id: int) -> list[Attachment]:
        """Get all attachments for a given message.

        Args:
            message_id: ID of the message to fetch attachments for

        Returns:
            List of Attachment objects ordered by id ascending
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, message_id, attachment_path, original_filename,
                       content_type, file_size
                FROM attachment
                WHERE message_id = ?
                ORDER BY id ASC
                """,
                (message_id,),
            )
            return [
                Attachment(
                    id=row[0], message_id=row[1], attachment_path=row[2],
                    original_filename=row[3], content_type=row[4], file_size=row[5],
                )
                for row in cursor.fetchall()
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get attachments by message: {e}")
            raise StorageError(f"Failed to get attachments by message: {e}") from e


class SyncRepository:
    """Repository for tracking sync operations."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def record(self, sync_type: str) -> int:
        """Record a completed sync operation (legacy helper).

        Args:
            sync_type: Either 'email' or 'linkedin'

        Returns:
            The id of the new sync record
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                "INSERT INTO sync (sync_type, sync_time, completed_at) "
                "VALUES (?, datetime('now'), datetime('now'))",
                (sync_type,),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        except sqlite3.Error as e:
            logger.error(f"Failed to record sync: {e}")
            raise StorageError(f"Failed to record sync: {e}") from e

    def start(self, sync_type: str, output_dir: str) -> int:
        """Create an ongoing sync row. Errors if one already exists.

        Args:
            sync_type: Either 'email' or 'linkedin'
            output_dir: The output folder name for this sync

        Returns:
            The id of the new sync record
        """
        conn = self._db.connect()
        existing = self.get_ongoing(sync_type)
        if existing is not None:
            raise StorageError(
                f"An ongoing {sync_type} sync already exists "
                f"(id={existing[0]}, output_dir={existing[2]})"
            )
        try:
            cursor = conn.execute(
                "INSERT INTO sync (sync_type, sync_time, output_dir) "
                "VALUES (?, datetime('now'), ?)",
                (sync_type, output_dir),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        except sqlite3.Error as e:
            logger.error(f"Failed to start sync: {e}")
            raise StorageError(f"Failed to start sync: {e}") from e

    def get_ongoing(self, sync_type: str) -> tuple[int, str, str] | None:
        """Get the ongoing sync for a given type.

        Returns:
            (id, sync_time, output_dir) or None if no ongoing sync
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                "SELECT id, sync_time, output_dir FROM sync "
                "WHERE sync_type = ? AND completed_at IS NULL "
                "ORDER BY sync_time DESC LIMIT 1",
                (sync_type,),
            )
            row = cursor.fetchone()
            return (row[0], row[1], row[2]) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get ongoing sync: {e}")
            raise StorageError(f"Failed to get ongoing sync: {e}") from e

    def complete(self, sync_id: int) -> None:
        """Mark a sync as completed."""
        conn = self._db.connect()
        try:
            conn.execute(
                "UPDATE sync SET completed_at = datetime('now') WHERE id = ?",
                (sync_id,),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to complete sync: {e}")
            raise StorageError(f"Failed to complete sync: {e}") from e

    def get_last(self, sync_type: str) -> str | None:
        """Get the timestamp of the most recent *completed* sync of a given type.

        Args:
            sync_type: Either 'email' or 'linkedin'

        Returns:
            ISO datetime string of the last completed sync, or None if never synced
        """
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                "SELECT sync_time FROM sync "
                "WHERE sync_type = ? AND completed_at IS NOT NULL "
                "ORDER BY sync_time DESC LIMIT 1",
                (sync_type,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get last sync: {e}")
            raise StorageError(f"Failed to get last sync: {e}") from e
