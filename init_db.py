#!/usr/bin/env python3
"""Initialize the database schema."""

from dm_bot.storage import DatabaseManager
from dm_bot.config import setup_logging

if __name__ == "__main__":
    setup_logging()
    db = DatabaseManager()
    db.connect()
    db.initialize_schema()
    print(f"✓ Database initialized at: {db.db_path}")
    db.close()
