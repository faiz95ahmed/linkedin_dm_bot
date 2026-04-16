"""SQLite-backed logging handler for dm_bot.

Writes log records to the `log` table in dm_bot.db via a background
thread so that logging never blocks the caller.
"""

import logging
import queue
import sqlite3
import threading
from datetime import datetime
from pathlib import Path


class SQLiteHandler(logging.Handler):
    """Non-blocking logging handler that persists records to SQLite."""

    def __init__(self, db_path: Path, run_id: str, command: str, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._db_path = db_path
        self._run_id = run_id
        self._command = command
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="sqlite-log-worker")
        self._thread.start()

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        self._queue.put(record)

    def close(self) -> None:
        self._queue.put(None)  # sentinel
        self._thread.join(timeout=5.0)
        super().close()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            return

        try:
            while True:
                record = self._queue.get()
                if record is None:
                    break
                self._insert(conn, record)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _insert(self, conn: sqlite3.Connection, record: logging.LogRecord) -> None:
        try:
            self.format(record)  # populates record.exc_text
            ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.") + f"{int(record.msecs):03d}"
            conn.execute(
                """
                INSERT INTO log
                    (run_id, command, ts, level, level_no, logger, module, func, lineno, message, exc_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._run_id,
                    self._command,
                    ts,
                    record.levelname,
                    record.levelno,
                    record.name,
                    record.module,
                    record.funcName,
                    record.lineno,
                    record.getMessage(),
                    record.exc_text or None,
                ),
            )
            conn.commit()
        except Exception:
            pass  # log failures must never crash the bot
