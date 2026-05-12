"""One-time migration: index existing JSON analysis files into SQLite.

Can be run standalone: python -m dashboard.migrate_to_sqlite
Or triggered automatically on first dashboard launch when DB is empty.
Idempotent — safe to run multiple times.
"""

import json
import logging
from pathlib import Path

from tradingagents.default_config import DEFAULT_CONFIG
from dashboard.db import get_db, index_analysis, store_memory_entry, _SCHEMA_VERSION

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(DEFAULT_CONFIG["results_dir"])
MEMORY_LOG = Path(DEFAULT_CONFIG["memory_log_path"])


def run_migration(progress_callback=None):
    """Migrate all existing JSON files and memory log into SQLite.

    Args:
        progress_callback: Optional callable(current, total, message) for UI updates.
    """
    # Check if migration already completed
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()
    existing_count = row[0] if row else 0

    # Scan JSON files
    json_files = []
    if RESULTS_DIR.exists():
        for ticker_dir in RESULTS_DIR.iterdir():
            if not ticker_dir.is_dir():
                continue
            log_dir = ticker_dir / "TradingAgentsStrategy_logs"
            if not log_dir.exists():
                continue
            json_files.extend(log_dir.glob("full_states_log_*.json"))

    total = len(json_files)
    indexed = 0
    skipped = 0

    logger.info("Migration: found %d JSON files (%d already in DB)", total, existing_count)

    for i, json_file in enumerate(json_files):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if index_analysis(json_file, data):
                indexed += 1
            else:
                skipped += 1
        except Exception as e:
            logger.warning("Migration: skipped %s: %s", json_file.name, e)
            skipped += 1

        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(i + 1, total, f"Indexed {indexed} analyses...")

    # Migrate memory log
    memory_migrated = _migrate_memory_log()

    logger.info(
        "Migration complete: %d indexed, %d skipped, %d memory entries",
        indexed, skipped, memory_migrated,
    )

    if progress_callback:
        progress_callback(total, total, f"Done: {indexed} analyses, {memory_migrated} memory entries")

    return {"indexed": indexed, "skipped": skipped, "memory_entries": memory_migrated}


def _migrate_memory_log() -> int:
    """Parse existing memory markdown and insert into SQLite."""
    if not MEMORY_LOG.exists():
        return 0

    try:
        from tradingagents.agents.utils.memory import TradingMemoryLog
        log = TradingMemoryLog({"memory_log_path": str(MEMORY_LOG)})
        entries = log.load_entries()
    except Exception as e:
        logger.warning("Memory migration failed to parse: %s", e)
        return 0

    count = 0
    for entry in entries:
        ticker = entry.get("ticker", "")
        trade_date = entry.get("date", "")
        rating = entry.get("rating", "")
        decision = entry.get("decision", "")

        if not ticker or not trade_date:
            continue

        if store_memory_entry(ticker, trade_date, rating, decision):
            # If resolved, update with outcome
            if not entry.get("pending") and entry.get("raw") is not None:
                try:
                    from dashboard.db import update_memory_outcome
                    raw = float(entry["raw"].rstrip("%")) / 100 if isinstance(entry["raw"], str) else 0
                    alpha = float(entry["alpha"].rstrip("%")) / 100 if isinstance(entry.get("alpha"), str) and entry["alpha"] != "n/a" else 0
                    holding = int(entry["holding"].rstrip("d")) if isinstance(entry.get("holding"), str) and entry["holding"] != "n/a" else 5
                    update_memory_outcome(ticker, trade_date, raw, alpha, holding, entry.get("reflection", ""))
                except (ValueError, TypeError):
                    pass
            count += 1

    return count


def needs_migration() -> bool:
    """Check if migration should run (DB exists but is empty, and JSON files exist)."""
    try:
        conn = get_db()
        row = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()
        if row[0] > 0:
            return False  # Already has data
    except Exception:
        return False

    # Check if JSON files exist
    if RESULTS_DIR.exists():
        for ticker_dir in RESULTS_DIR.iterdir():
            if ticker_dir.is_dir():
                log_dir = ticker_dir / "TradingAgentsStrategy_logs"
                if log_dir.exists() and any(log_dir.glob("full_states_log_*.json")):
                    return True
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration(lambda cur, tot, msg: print(f"  [{cur}/{tot}] {msg}"))
    print(f"\nMigration result: {result}")
