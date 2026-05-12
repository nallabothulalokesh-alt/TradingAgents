# Design Document — Sprint 1B: SQLite Data Layer + Bug Fixes + Memory Migration

## Overview

Establish the data foundation: fix critical thread-safety bugs, migrate the memory log to a queryable format, and introduce SQLite as the dashboard's read layer. This sprint has no UI changes — it's all backend/infrastructure.

## Part 1: Bug Fixes (Thread Safety)

### Bug 4: RunState `start()` method

Add atomic initialization:
```python
class RunState:
    def start(self, ticker: str, trade_date: str, agent_status: dict):
        with self._lock:
            self.running = True
            self.ticker = ticker
            self.trade_date = trade_date
            self.agent_status = agent_status
```

Remove redundant assignments in `_worker()` (runner.py lines 298-304).

### Bug 2: No session_state from background threads

Current `_dispatch_next()` is already called from main thread. The `_worker()` in watchlist.py only writes to `_results_buffer`. Verify no code path in `_worker()` touches `st.session_state`. Add a code comment documenting this contract.

### Bug 3: Session-scoped results buffer

Replace module-level `_results_buffer: List` with:
```python
_results_buffers: Dict[str, List] = {}
_buffer_timestamps: Dict[str, float] = {}
_results_lock = threading.Lock()
```

Each session gets a UUID stored in `st.session_state["_wl_session_id"]`. Workers receive the session_id at dispatch and write to the correct buffer.

Cleanup: during drain, remove buffers where `_buffer_timestamps[sid] < now - 3600` AND buffer is empty.

## Part 2: Bug Fixes (Data Integrity)

### Bug 5: Trader plan key fallback
One-line fix in 3 files: `data.get("trader_investment_decision") or data.get("trader_investment_plan")`

### Bug 6: History deduplication
In `list_history()`, after scanning all files, deduplicate by `(ticker, date)` keeping the newest file (by mtime).

### Bug 15: sanitize_report() allowlist
Replace the aggressive regex with:
```python
_ALLOWED_TAGS = {'b','i','em','strong','table','tr','td','th','ul','ol','li',
                 'p','br','h1','h2','h3','h4','h5','h6','blockquote','code',
                 'pre','span','div','a','hr'}

def sanitize_report(text):
    # 1. Remove known bad patterns (tool_calls, script)
    cleaned = re.sub(r'<tool_calls>.*?</tool_calls>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'</?(?:antml:)?(?:tool_call|parameter)[^>]*>', '', cleaned)
    # 2. Strip non-allowlisted tags (keep content)
    def strip_tag(m):
        tag_name = re.match(r'</?(\w+)', m.group(0))
        if tag_name and tag_name.group(1).lower() in _ALLOWED_TAGS:
            return m.group(0)  # keep
        return ''  # strip tag, keep surrounding content
    cleaned = re.sub(r'</?[a-zA-Z][^>]*>', strip_tag, cleaned)
    # 3. Collapse whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned or "⚠️ Report generation failed..."
```

### Bug 16: HTML escaping
Add `import html` and wrap extracted values:
```python
price_target = html.escape(pt_match.group(1).strip()) if pt_match else None
```

### Bug 11: safe_ticker_component whitespace
Add before `.strip()`:
```python
if any(c in value for c in ' \t\n\r'):
    raise ValueError(f"Ticker contains whitespace: {value!r}")
```

### Bug 12: Delete broken test file
Delete `tests/test_ticker_symbol_handling.py`.

## Part 3: SQLite Data Layer

### Module: `dashboard/db.py`

```python
import sqlite3, threading, logging
from pathlib import Path

_local = threading.local()
_DB_PATH = Path("~/.tradingagents/tradingagents.db").expanduser()

def get_db() -> sqlite3.Connection:
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(str(_DB_PATH), timeout=10)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA cache_size=-64000")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.row_factory = sqlite3.Row
        _ensure_schema(_local.conn)
    return _local.conn

def is_db_available() -> bool:
    try:
        get_db()
        return True
    except Exception:
        return False
```

### Schema creation in `_ensure_schema(conn)`:
Creates all tables and indexes as specified in sqlite-data-layer Req 1.

### Post-save hook: `index_analysis(json_path, data)`
Called from `runner.py` after `graph_obj._log_state()`. Extracts lightweight fields, INSERTs into `analyses` + `reports` tables.

**IMPORTANT — Circular Import Prevention:** `index_analysis()` in `db.py` needs to compute conviction. It MUST NOT import `compute_conviction()` from `utils.py` (because `utils.py` imports from `db.py`). Instead, `index_analysis()` SHALL compute conviction inline using the same logic (count non-empty report fields). This duplicates ~5 lines of logic but prevents a circular import. Alternatively, the caller (`runner.py`) can compute conviction and pass it as a parameter to `index_analysis()`.

### Migration script: `dashboard/migrate_to_sqlite.py`
Scans all JSON files, calls `index_analysis()` for each. Runs in background thread on first launch.

## Part 4: Memory Migration

### Write Strategy: Triple-Write (Markdown + JSON + SQLite)

When all specs are implemented, `store_decision()` writes to THREE locations:
1. **Markdown** (`trading_memory.md`) — human-readable, always written (existing behavior)
2. **JSON** (`trading_memory.json`) — machine-readable portable backup (memory-log-json-migration spec)
3. **SQLite** (`tradingagents.db` → `memory_entries` table) — queryable read layer (sqlite-data-layer spec)

**Read priority:** SQLite → JSON → Markdown (first available wins).

This is intentional: markdown for humans, JSON for portability/backup, SQLite for performance. The JSON file becomes redundant once SQLite is stable, but is kept for the transition period and for users who want to export/import data.

### Dual-write in `TradingMemoryLog`

Add optional SQLite write path:
```python
class TradingMemoryLog:
    def __init__(self, config):
        ...
        self._db_path = config.get("sqlite_db_path")  # None = no SQLite

    def store_decision(self, ticker, trade_date, final_trade_decision):
        # Existing markdown write (unchanged)
        ...
        # New: SQLite write
        if self._db_path:
            self._sqlite_store(ticker, trade_date, final_trade_decision)
```

The dashboard passes `sqlite_db_path` via the config dict when calling `run_analysis()`.

## Files Modified

| File | Changes |
|------|---------|
| `dashboard/utils.py` | RunState.start(), sanitize_report() rewrite, Bug 5/6 fixes |
| `dashboard/runner.py` | Remove redundant _worker assignments, add index_analysis() call |
| `dashboard/views/watchlist.py` | Session-scoped buffer (Bug 3) |
| `dashboard/views/history.py` | Bug 5 trader plan fallback |
| `dashboard/views/compare.py` | Bug 5 trader plan fallback |
| `dashboard/db.py` | NEW — SQLite module |
| `dashboard/migrate_to_sqlite.py` | NEW — migration script |
| `tradingagents/agents/utils/memory.py` | Dual-write to SQLite |
| `tradingagents/dataflows/utils.py` | Bug 11 whitespace check |
| `tests/test_ticker_symbol_handling.py` | DELETE (Bug 12) |
