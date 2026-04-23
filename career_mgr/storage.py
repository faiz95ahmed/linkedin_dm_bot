"""Data storage models and database manager for career lead tracking."""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Types
LeadStatus = Literal["active", "declined", "on_hold", "closed", "offer_accepted"]
LeadSource = Literal["linkedin", "email", "offline"]
ProcessStage = Literal[
    "initial_call",
    "recruiter_screen",
    "hiring_manager",
    "technical_interview",
    "take_home",
    "onsite",
    "final_round",
    "offer",
    "negotiation",
]
ProcessStatus = Literal["upcoming", "completed", "cancelled", "rescheduled", "no_show"]

# Default DB path
DEFAULT_DB_PATH: Path = Path.home() / "CAREER" / "career.db"


# =============================================================================
# Data Models
# =============================================================================


class Lead(BaseModel):
    company: str
    role_title: str
    created_at: datetime
    updated_at: datetime
    status: LeadStatus = "active"
    id: int | None = None
    source: LeadSource | None = None
    source_ref: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "GBP"
    notes: str | None = None


class Process(BaseModel):
    lead_id: int
    sequence: int
    stage: ProcessStage
    created_at: datetime
    updated_at: datetime
    status: ProcessStatus = "upcoming"
    id: int | None = None
    scheduled_at: datetime | None = None
    outcome: str | None = None
    notes: str | None = None


# =============================================================================
# Exceptions
# =============================================================================


class CareerStorageError(Exception):
    pass


class LeadNotFoundError(CareerStorageError):
    pass


class ProcessNotFoundError(CareerStorageError):
    pass


# =============================================================================
# DateTime adapters (same pattern as dm_bot)
# =============================================================================


def _adapt_datetime(dt: datetime) -> str:
    return dt.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    return datetime.fromisoformat(val.decode())


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("DATETIME", _convert_datetime)


# =============================================================================
# Database Manager
# =============================================================================


class CareerDatabaseManager:
    _SCHEMA_SQL = """
        CREATE TABLE IF NOT EXISTS lead (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company         TEXT    NOT NULL,
            role_title      TEXT    NOT NULL,
            source          TEXT    CHECK (source IN ('linkedin', 'email', 'offline')),
            source_ref      TEXT,
            status          TEXT    NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'declined', 'on_hold', 'closed', 'offer_accepted')),
            salary_min      INTEGER,
            salary_max      INTEGER,
            salary_currency TEXT    DEFAULT 'GBP',
            notes           TEXT,
            created_at      DATETIME NOT NULL,
            updated_at      DATETIME NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_lead_status     ON lead(status);
        CREATE INDEX IF NOT EXISTS idx_lead_company    ON lead(company);
        CREATE INDEX IF NOT EXISTS idx_lead_updated_at ON lead(updated_at);

        CREATE TABLE IF NOT EXISTS process (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id         INTEGER NOT NULL,
            sequence        INTEGER NOT NULL,
            stage           TEXT    NOT NULL
                            CHECK (stage IN (
                                'initial_call', 'recruiter_screen', 'hiring_manager',
                                'technical_interview', 'take_home', 'onsite',
                                'final_round', 'offer', 'negotiation'
                            )),
            scheduled_at    DATETIME,
            status          TEXT    NOT NULL DEFAULT 'upcoming'
                            CHECK (status IN ('upcoming', 'completed', 'cancelled', 'rescheduled', 'no_show')),
            outcome         TEXT,
            notes           TEXT,
            created_at      DATETIME NOT NULL,
            updated_at      DATETIME NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES lead(id),
            UNIQUE (lead_id, sequence)
        );

        CREATE INDEX IF NOT EXISTS idx_process_lead_id      ON process(lead_id);
        CREATE INDEX IF NOT EXISTS idx_process_scheduled_at  ON process(scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_process_status        ON process(status);
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection

        try:
            if str(self.db_path) != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

            self._connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            self._connection.execute("PRAGMA foreign_keys = ON")
            return self._connection
        except (sqlite3.Error, OSError) as e:
            raise CareerStorageError(f"Failed to connect to database: {e}") from e

    def initialize_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(self._SCHEMA_SQL)
            conn.commit()
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to initialize schema: {e}") from e

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


# =============================================================================
# Lead Repository
# =============================================================================


class LeadRepository:
    def __init__(self, db: CareerDatabaseManager) -> None:
        self._db = db

    def create(self, lead: Lead) -> Lead:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO lead (company, role_title, source, source_ref, status,
                                  salary_min, salary_max, salary_currency, notes,
                                  created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead.company,
                    lead.role_title,
                    lead.source,
                    lead.source_ref,
                    lead.status,
                    lead.salary_min,
                    lead.salary_max,
                    lead.salary_currency,
                    lead.notes,
                    lead.created_at,
                    lead.updated_at,
                ),
            )
            conn.commit()
            return lead.model_copy(update={"id": cursor.lastrowid})
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to create lead: {e}") from e

    def get_by_id(self, lead_id: int) -> Lead | None:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, company, role_title, source, source_ref, status,
                       salary_min, salary_max, salary_currency, notes,
                       created_at, updated_at
                FROM lead WHERE id = ?
                """,
                (lead_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return Lead(
                id=row[0], company=row[1], role_title=row[2], source=row[3],
                source_ref=row[4], status=row[5], salary_min=row[6],
                salary_max=row[7], salary_currency=row[8], notes=row[9],
                created_at=row[10], updated_at=row[11],
            )
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to get lead: {e}") from e

    def update(self, lead_id: int, **fields: object) -> Lead:
        lead = self.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id} not found")

        fields["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        set_clauses = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [lead_id]

        conn = self._db.connect()
        try:
            conn.execute(
                f"UPDATE lead SET {set_clauses} WHERE id = ?",  # noqa: S608
                values,
            )
            conn.commit()
            return self.get_by_id(lead_id)  # type: ignore[return-value]
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to update lead: {e}") from e

    def list_by_status(self, status: LeadStatus) -> list[Lead]:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, company, role_title, source, source_ref, status,
                       salary_min, salary_max, salary_currency, notes,
                       created_at, updated_at
                FROM lead WHERE status = ? ORDER BY updated_at DESC
                """,
                (status,),
            )
            return [self._row_to_lead(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to list leads: {e}") from e

    def list_all(self) -> list[Lead]:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, company, role_title, source, source_ref, status,
                       salary_min, salary_max, salary_currency, notes,
                       created_at, updated_at
                FROM lead ORDER BY updated_at DESC
                """
            )
            return [self._row_to_lead(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to list leads: {e}") from e

    @staticmethod
    def _row_to_lead(row: tuple) -> Lead:
        return Lead(
            id=row[0], company=row[1], role_title=row[2], source=row[3],
            source_ref=row[4], status=row[5], salary_min=row[6],
            salary_max=row[7], salary_currency=row[8], notes=row[9],
            created_at=row[10], updated_at=row[11],
        )


# =============================================================================
# Process Repository
# =============================================================================


class ProcessRepository:
    def __init__(self, db: CareerDatabaseManager) -> None:
        self._db = db

    def create(self, process: Process) -> Process:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO process (lead_id, sequence, stage, scheduled_at, status,
                                     outcome, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    process.lead_id,
                    process.sequence,
                    process.stage,
                    process.scheduled_at,
                    process.status,
                    process.outcome,
                    process.notes,
                    process.created_at,
                    process.updated_at,
                ),
            )
            conn.commit()
            return process.model_copy(update={"id": cursor.lastrowid})
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to create process: {e}") from e

    def get_by_id(self, process_id: int) -> Process | None:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, lead_id, sequence, stage, scheduled_at, status,
                       outcome, notes, created_at, updated_at
                FROM process WHERE id = ?
                """,
                (process_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_process(row)
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to get process: {e}") from e

    def get_stages_for_lead(self, lead_id: int) -> list[Process]:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, lead_id, sequence, stage, scheduled_at, status,
                       outcome, notes, created_at, updated_at
                FROM process WHERE lead_id = ? ORDER BY sequence ASC
                """,
                (lead_id,),
            )
            return [self._row_to_process(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to get stages: {e}") from e

    def update(self, process_id: int, **fields: object) -> Process:
        proc = self.get_by_id(process_id)
        if proc is None:
            raise ProcessNotFoundError(f"Process {process_id} not found")

        fields["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        set_clauses = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [process_id]

        conn = self._db.connect()
        try:
            conn.execute(
                f"UPDATE process SET {set_clauses} WHERE id = ?",  # noqa: S608
                values,
            )
            conn.commit()
            return self.get_by_id(process_id)  # type: ignore[return-value]
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to update process: {e}") from e

    def list_upcoming(self) -> list[Process]:
        conn = self._db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, lead_id, sequence, stage, scheduled_at, status,
                       outcome, notes, created_at, updated_at
                FROM process WHERE status = 'upcoming'
                ORDER BY scheduled_at ASC NULLS LAST
                """
            )
            return [self._row_to_process(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise CareerStorageError(f"Failed to list upcoming: {e}") from e

    def next_sequence(self, lead_id: int) -> int:
        conn = self._db.connect()
        cursor = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM process WHERE lead_id = ?",
            (lead_id,),
        )
        return cursor.fetchone()[0]  # type: ignore[index]

    @staticmethod
    def _row_to_process(row: tuple) -> Process:
        return Process(
            id=row[0], lead_id=row[1], sequence=row[2], stage=row[3],
            scheduled_at=row[4], status=row[5], outcome=row[6], notes=row[7],
            created_at=row[8], updated_at=row[9],
        )
