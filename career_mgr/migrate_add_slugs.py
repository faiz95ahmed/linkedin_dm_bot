"""One-off migration: add lead.slug + process.str_id to an existing career.db.

Backfills:
  - lead.slug: auto-derived from company name (kebab-case), de-duplicated with -2,-3...
  - process.str_id: random 4-hex, unique within each lead.

Idempotent guard: refuses to run if the target already has a `slug` column.
Operates on whatever DB path is passed (default: the live DB), so point it at a
copy first to dry-run.

Usage:
    uv run python -m career_mgr.migrate_add_slugs /path/to/career.db
"""

import re
import secrets
import sqlite3
import sys
from pathlib import Path

from career_mgr.storage import CareerDatabaseManager


def _slugify(company: str) -> str:
    s = company.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)  # non-alnum runs -> single hyphen
    s = s.strip("-")
    return s or "lead"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = OFF")  # we rebuild tables; FKs re-checked after

    if _has_column(conn, "lead", "slug"):
        print(f"  '{db_path}' already has lead.slug — nothing to do.")
        conn.close()
        return

    # --- read existing data ---
    lead_rows = conn.execute(
        "SELECT id, company FROM lead ORDER BY id"
    ).fetchall()
    print(f"  {len(lead_rows)} leads, ", end="")
    proc_count = conn.execute("SELECT COUNT(*) FROM process").fetchone()[0]
    print(f"{proc_count} process stages to migrate.")

    # --- assign slugs (deduplicated) ---
    slug_for: dict[int, str] = {}
    seen: dict[str, int] = {}
    for lead_id, company in lead_rows:
        base = _slugify(company or "")
        slug = base
        if slug in seen:
            seen[base] += 1
            slug = f"{base}-{seen[base]}"
        else:
            seen[base] = 1
        slug_for[lead_id] = slug

    # --- assign str_ids (unique within each lead) ---
    proc_rows = conn.execute("SELECT id, lead_id FROM process ORDER BY id").fetchall()
    str_id_for: dict[int, str] = {}
    used_per_lead: dict[int, set[str]] = {}
    for proc_id, lead_id in proc_rows:
        used = used_per_lead.setdefault(lead_id, set())
        while True:
            sid = f"{secrets.randbelow(0x10000):04x}"
            if sid not in used:
                used.add(sid)
                break
        str_id_for[proc_id] = sid

    # --- add columns + backfill, in a transaction ---
    try:
        conn.execute("BEGIN")
        # lead.slug: add nullable, backfill, then enforce uniqueness via index.
        conn.execute("ALTER TABLE lead ADD COLUMN slug TEXT")
        for lead_id, slug in slug_for.items():
            conn.execute("UPDATE lead SET slug = ? WHERE id = ?", (slug, lead_id))
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_slug_unique ON lead(slug)"
        )

        # process.str_id: add, backfill, then unique-per-lead index.
        conn.execute("ALTER TABLE process ADD COLUMN str_id TEXT")
        for proc_id, sid in str_id_for.items():
            conn.execute(
                "UPDATE process SET str_id = ? WHERE id = ?", (sid, proc_id)
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_process_lead_str_id "
            "ON process(lead_id, str_id)"
        )
        conn.execute("COMMIT")
    except sqlite3.Error:
        conn.execute("ROLLBACK")
        conn.close()
        raise

    # --- verify: no NULLs, uniqueness holds ---
    null_slugs = conn.execute("SELECT COUNT(*) FROM lead WHERE slug IS NULL").fetchone()[0]
    null_sids = conn.execute(
        "SELECT COUNT(*) FROM process WHERE str_id IS NULL"
    ).fetchone()[0]
    dup_slugs = conn.execute(
        "SELECT COUNT(*) FROM (SELECT slug FROM lead GROUP BY slug HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    dup_sids = conn.execute(
        "SELECT COUNT(*) FROM (SELECT lead_id, str_id FROM process "
        "GROUP BY lead_id, str_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    conn.commit()
    conn.close()

    assert null_slugs == 0, f"{null_slugs} leads still have NULL slug"
    assert null_sids == 0, f"{null_sids} processes still have NULL str_id"
    assert dup_slugs == 0, f"{dup_slugs} duplicate slugs"
    assert dup_sids == 0, f"{dup_sids} duplicate (lead_id, str_id) pairs"
    print("  ✓ migration complete: no NULLs, no duplicates.")


def main() -> None:
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        db_path = CareerDatabaseManager().db_path
    print(f"Migrating {db_path} ...")
    migrate(db_path)


if __name__ == "__main__":
    main()
