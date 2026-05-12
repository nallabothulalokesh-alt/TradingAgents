"""SQLite data layer for the TradingAgents dashboard.

Provides a fast, queryable read layer over the JSON analysis files.
The pipeline continues to write JSON; this module indexes them into SQLite
for instant queries. Falls back gracefully if the DB is unavailable.
"""

import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

_TRADINGAGENTS_HOME = Path(DEFAULT_CONFIG.get("results_dir", "~/.tradingagents/logs")).parent
_DB_PATH = _TRADINGAGENTS_HOME / "tradingagents.db"
_local = threading.local()

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    rating TEXT,
    executive_summary TEXT,
    price_target TEXT,
    time_horizon TEXT,
    conviction TEXT,
    portfolio_context TEXT,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, trade_date, source_file)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(analysis_id, report_type)
);

CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    rating TEXT,
    decision_text TEXT,
    raw_return REAL,
    alpha_return REAL,
    holding_days INTEGER,
    reflection TEXT,
    pending INTEGER NOT NULL DEFAULT 1,
    portfolio_context TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, trade_date)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    analysis_ticker TEXT,
    analysis_date TEXT,
    mode TEXT NOT NULL DEFAULT 'single',
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    shares REAL NOT NULL,
    cost_basis REAL,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_analyses_ticker ON analyses(ticker);
CREATE INDEX IF NOT EXISTS idx_analyses_trade_date ON analyses(trade_date);
CREATE INDEX IF NOT EXISTS idx_analyses_ticker_date ON analyses(ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_memory_ticker ON memory_entries(ticker);
CREATE INDEX IF NOT EXISTS idx_memory_pending ON memory_entries(pending);
CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_analysis ON chat_messages(analysis_ticker, analysis_date);
"""


# ── Connection management ─────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Get a thread-local SQLite connection with WAL mode enabled."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(_DB_PATH), timeout=10)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA cache_size=-64000")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.row_factory = sqlite3.Row
        _ensure_schema(_local.conn)
    return _local.conn


def close_db():
    """Close the thread-local connection."""
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def is_db_available() -> bool:
    """Check if SQLite is usable."""
    try:
        get_db()
        return True
    except Exception:
        return False


def _ensure_schema(conn: sqlite3.Connection):
    """Create tables if they don't exist and apply migrations."""
    conn.executescript(_SCHEMA_SQL)
    # Insert schema version if not present
    cur = conn.execute("SELECT MAX(version) FROM schema_version")
    row = cur.fetchone()
    if row[0] is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
        conn.commit()


# ── Rating extraction (inline to avoid circular import with utils.py) ─────────

_RATING_RE = re.compile(
    r'\b(Buy|Overweight|Hold|Underweight|Sell)\b', re.IGNORECASE
)


def _extract_rating_inline(text: str) -> str:
    """Extract rating from decision text without importing from utils."""
    if not text:
        return ""
    m = _RATING_RE.search(text)
    return m.group(1).capitalize() if m else ""


def _compute_conviction_inline(data: dict) -> str:
    """Compute conviction level inline (avoids circular import with utils.py)."""
    fields = ["market_report", "news_report", "fundamentals_report",
              "sentiment_report", "investment_plan", "trader_investment_plan",
              "final_trade_decision"]
    score = sum(1 for f in fields if data.get(f))
    if score >= 6:
        return "High"
    elif score >= 4:
        return "Medium"
    return "Low"


_PT_RE = re.compile(r'(?i)\*\*Price\s+Target\*\*[:\s]*([^\n]+)')
_TH_RE = re.compile(r'(?i)\*\*Time\s+Horizon\*\*[:\s]*([^\n]+)')
_ES_RE = re.compile(r'(?i)\*\*Executive\s+Summary\*\*[:\s]*([^\n]+)')


# ── Index operations ──────────────────────────────────────────────────────────

def index_analysis(json_path: Path, data: dict) -> bool:
    """Index a completed analysis into SQLite. Idempotent.

    Returns True on success, False on failure (never raises).
    """
    for attempt in range(3):
        try:
            conn = get_db()
            ticker = data.get("company_of_interest", "")
            trade_date = data.get("trade_date", "")
            decision_text = data.get("final_trade_decision", "")
            rating = _extract_rating_inline(decision_text)
            conviction = _compute_conviction_inline(data)

            pt_match = _PT_RE.search(decision_text)
            th_match = _TH_RE.search(decision_text)
            es_match = _ES_RE.search(decision_text)

            price_target = pt_match.group(1).strip() if pt_match else None
            time_horizon = th_match.group(1).strip() if th_match else None
            exec_summary = es_match.group(1).strip() if es_match else None

            with conn:
                cur = conn.execute(
                    """INSERT OR REPLACE INTO analyses
                       (ticker, trade_date, rating, executive_summary, price_target,
                        time_horizon, conviction, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ticker, trade_date, rating, exec_summary, price_target,
                     time_horizon, conviction, str(json_path)),
                )
                analysis_id = cur.lastrowid

                # Index report sections
                report_fields = [
                    ("market_report", data.get("market_report")),
                    ("news_report", data.get("news_report")),
                    ("fundamentals_report", data.get("fundamentals_report")),
                    ("sentiment_report", data.get("sentiment_report")),
                    ("investment_plan", data.get("investment_plan")),
                    ("trader_investment_plan",
                     data.get("trader_investment_decision") or data.get("trader_investment_plan")),
                    ("final_trade_decision", decision_text),
                ]
                for report_type, content in report_fields:
                    if content:
                        conn.execute(
                            """INSERT OR REPLACE INTO reports (analysis_id, report_type, content)
                               VALUES (?, ?, ?)""",
                            (analysis_id, report_type, content),
                        )
            return True

        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 2:
                time.sleep(0.1 * (attempt + 1))
                continue
            logger.warning("index_analysis failed: %s", e)
            return False
        except Exception as e:
            logger.warning("index_analysis failed: %s", e)
            return False
    return False


# ── Query operations ──────────────────────────────────────────────────────────

def list_analyses(
    ticker: str = None,
    date_from: str = None,
    date_to: str = None,
    rating: str = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query analyses with optional filters. Returns lightweight dicts."""
    try:
        conn = get_db()
    except Exception:
        return []

    sql = "SELECT id, ticker, trade_date, rating, executive_summary, price_target, time_horizon, conviction, portfolio_context, source_file, created_at FROM analyses WHERE 1=1"
    params: list = []

    if ticker:
        sql += " AND ticker LIKE ?"
        params.append(f"%{ticker}%")
    if date_from:
        sql += " AND trade_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND trade_date <= ?"
        params.append(date_to)
    if rating:
        sql += " AND rating = ?"
        params.append(rating)

    sql += " ORDER BY trade_date DESC, created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("list_analyses query failed: %s", e)
        return []


def get_analysis_reports(analysis_id: int) -> Dict[str, str]:
    """Load all report text for a single analysis."""
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT report_type, content FROM reports WHERE analysis_id = ?",
            (analysis_id,),
        ).fetchall()
        return {row["report_type"]: row["content"] for row in rows}
    except Exception as e:
        logger.warning("get_analysis_reports failed: %s", e)
        return {}


# ── Memory entry operations ───────────────────────────────────────────────────

def store_memory_entry(
    ticker: str, trade_date: str, rating: str, decision_text: str
) -> bool:
    """Insert a pending memory entry into SQLite."""
    try:
        conn = get_db()
        with conn:
            conn.execute(
                """INSERT OR IGNORE INTO memory_entries
                   (ticker, trade_date, rating, decision_text, pending)
                   VALUES (?, ?, ?, ?, 1)""",
                (ticker, trade_date, rating, decision_text),
            )
        return True
    except Exception as e:
        logger.warning("store_memory_entry failed: %s", e)
        return False


def update_memory_outcome(
    ticker: str, trade_date: str,
    raw_return: float, alpha_return: float, holding_days: int, reflection: str
) -> bool:
    """Update a pending memory entry with outcome data."""
    try:
        conn = get_db()
        with conn:
            conn.execute(
                """UPDATE memory_entries
                   SET raw_return=?, alpha_return=?, holding_days=?, reflection=?, pending=0
                   WHERE ticker=? AND trade_date=? AND pending=1""",
                (raw_return, alpha_return, holding_days, reflection, ticker, trade_date),
            )
        return True
    except Exception as e:
        logger.warning("update_memory_outcome failed: %s", e)
        return False


def load_memory_entries_db(
    ticker: str = None, pending_only: bool = False
) -> List[Dict[str, Any]]:
    """Query memory entries from SQLite."""
    try:
        conn = get_db()
    except Exception:
        return []

    sql = "SELECT * FROM memory_entries WHERE 1=1"
    params: list = []
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker)
    if pending_only:
        sql += " AND pending = 1"
    sql += " ORDER BY trade_date DESC"

    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("load_memory_entries_db failed: %s", e)
        return []


# ── Portfolio CRUD ────────────────────────────────────────────────────────────

def add_position(ticker: str, shares: float, cost_basis: float = None) -> bool:
    """Add a new lot/position for a ticker (supports multiple entries per ticker)."""
    try:
        conn = get_db()
        with conn:
            conn.execute(
                """INSERT INTO portfolio_positions (ticker, shares, cost_basis)
                   VALUES (?, ?, ?)""",
                (ticker.upper(), shares, cost_basis),
            )
        return True
    except Exception as e:
        logger.warning("add_position failed: %s", e)
        return False


def update_position(ticker: str, position_id: int, shares: float, cost_basis: float = None) -> bool:
    """Update a specific lot by its ID."""
    try:
        conn = get_db()
        with conn:
            conn.execute(
                "UPDATE portfolio_positions SET shares=?, cost_basis=?, updated_at=datetime('now') WHERE id=?",
                (shares, cost_basis, position_id),
            )
        return True
    except Exception as e:
        logger.warning("update_position failed: %s", e)
        return False


def remove_position(position_id: int) -> bool:
    """Remove a specific lot by its ID."""
    try:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM portfolio_positions WHERE id=?", (position_id,))
        return True
    except Exception as e:
        logger.warning("remove_position failed: %s", e)
        return False


def list_positions() -> List[Dict[str, Any]]:
    """List all portfolio lots with latest analysis info per ticker."""
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT p.id, p.ticker, p.shares, p.cost_basis, p.added_at, p.updated_at,
                   a.rating AS last_rating, a.trade_date AS last_analysis_date
            FROM portfolio_positions p
            LEFT JOIN (
                SELECT ticker, rating, trade_date,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) as rn
                FROM analyses
            ) a ON p.ticker = a.ticker AND a.rn = 1
            ORDER BY p.ticker, p.added_at
        """).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("list_positions failed: %s", e)
        return []
