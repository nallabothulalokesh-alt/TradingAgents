# Requirements Document — SQLite Data Layer

## Introduction

The TradingAgents dashboard currently stores all data as flat JSON files scattered across `~/.tradingagents/logs/{TICKER}/TradingAgentsStrategy_logs/` and a markdown memory log at `~/.tradingagents/memory/trading_memory.md`. This architecture has critical scaling problems:

1. **list_history()** must open and parse every JSON file (500KB-2MB each) to build a summary table — loading hundreds of MB into memory on every 30-second cache refresh.
2. **Querying by criteria** (e.g., "all runs where return > 5%", "all NVDA runs in the last month") requires full-scanning every file.
3. **The memory log** is a fragile markdown file parsed with regex.
4. **Chat history** is scattered across per-ticker directories with no efficient lookup.
5. **Portfolio data** (proposed) would add yet another JSON file to manage atomically.

This spec introduces a local SQLite database as the **read layer** for the dashboard. The agent pipeline continues to write JSON files as before (no pipeline changes), but a post-save indexing step populates SQLite. All dashboard reads go through SQLite, eliminating the need to scan/parse hundreds of files on every page load.

**Scope:** `dashboard/db.py` (new), `dashboard/utils.py` (read functions migrated), `dashboard/runner.py` (post-save hook), `tradingagents/agents/utils/memory.py` (dual-write to SQLite). No changes to the LangGraph pipeline, agent prompts, or data source tools.

**Dependencies:** None — this spec can be implemented independently. However, it **replaces** the memory-log-json-migration spec's read path. The memory JSON migration spec's write path (dual-write to JSON for portability) remains valid but the dashboard reads from SQLite instead.

---

## Glossary

- **DataStore**: The new SQLite database at `~/.tradingagents/tradingagents.db`.
- **Analysis_Record**: A row in the `analyses` table representing one completed analysis run.
- **Report_Record**: A row in the `reports` table containing the full text of one analyst report for a given analysis.
- **Memory_Entry**: A row in the `memory_entries` table representing one trading decision with optional return/reflection data.
- **Chat_Message**: A row in the `chat_messages` table representing one message in a chat conversation.
- **Portfolio_Position**: A row in the `portfolio_positions` table representing a user's holding.
- **Index_Hook**: The function called after the pipeline saves a JSON file, which extracts fields and inserts/updates the SQLite record.
- **Migration_Script**: A one-time script that reads all existing JSON files and markdown memory and populates the database.

---

## Requirements

### Requirement 1: Database Schema and Initialization

**User Story:** As a developer, I want a well-structured SQLite database that separates lightweight summary data from heavy report text, so that dashboard reads are fast and memory-efficient.

#### Acceptance Criteria

1. THE DataStore SHALL be a single SQLite file at `~/.tradingagents/tradingagents.db`.
2. THE DataStore SHALL be created automatically on first access if it does not exist.
3. THE DataStore SHALL contain the following tables:

```sql
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Lightweight analysis summary (what list_history_summary needs)
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    rating TEXT,                    -- Buy/Overweight/Hold/Underweight/Sell
    executive_summary TEXT,
    price_target TEXT,
    time_horizon TEXT,
    conviction TEXT,               -- High/Medium/Low
    portfolio_context TEXT,
    source_file TEXT NOT NULL,      -- path to the original JSON file
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, trade_date, source_file)
);

-- Heavy report text (loaded only on drill-in)
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,      -- market_report, news_report, fundamentals_report, sentiment_report, investment_plan, trader_investment_plan, final_trade_decision, investment_debate, risk_debate
    content TEXT NOT NULL,
    UNIQUE(analysis_id, report_type)
);

-- Memory log entries (replaces markdown parsing)
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
    pending INTEGER NOT NULL DEFAULT 1,  -- boolean: 1=pending, 0=resolved
    portfolio_context TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ticker, trade_date)
);

-- Chat history (replaces per-ticker JSON files)
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,  -- groups messages in one chat session
    analysis_ticker TEXT,           -- which analysis this chat is about
    analysis_date TEXT,
    mode TEXT NOT NULL DEFAULT 'single',  -- 'single' or 'multi'
    role TEXT NOT NULL,             -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Portfolio positions
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    shares REAL NOT NULL,
    cost_basis REAL,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

4. THE DataStore SHALL create indexes for common query patterns:

```sql
CREATE INDEX IF NOT EXISTS idx_analyses_ticker ON analyses(ticker);
CREATE INDEX IF NOT EXISTS idx_analyses_trade_date ON analyses(trade_date);
CREATE INDEX IF NOT EXISTS idx_analyses_ticker_date ON analyses(ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_analyses_rating ON analyses(rating);
CREATE INDEX IF NOT EXISTS idx_memory_ticker ON memory_entries(ticker);
CREATE INDEX IF NOT EXISTS idx_memory_pending ON memory_entries(pending);
CREATE INDEX IF NOT EXISTS idx_chat_conversation ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_analysis ON chat_messages(analysis_ticker, analysis_date);
```

5. THE DataStore SHALL insert `(1, datetime('now'))` into `schema_version` on creation.
6. THE `dashboard/db.py` module SHALL expose a `get_db() -> sqlite3.Connection` function that returns a connection with WAL mode enabled and foreign keys enforced. The connection SHALL be cached per-thread using `threading.local()`.

---

### Requirement 2: Post-Save Index Hook

**User Story:** As a user, I want my newly completed analyses to appear instantly in the dashboard without waiting for a full filesystem scan, so that the UI feels responsive.

#### Acceptance Criteria

1. THE `dashboard/runner.py` SHALL call `index_analysis(json_path: Path, data: dict)` after successfully saving a `full_states_log_*.json` file.
2. THE `index_analysis()` function (in `dashboard/db.py`) SHALL:
   - Extract lightweight fields: `ticker`, `trade_date`, `rating` (via signal processing regex), `executive_summary`, `price_target`, `time_horizon`, `conviction` (via `compute_conviction()`).
   - INSERT OR REPLACE into the `analyses` table.
   - INSERT OR REPLACE each report section into the `reports` table.
3. THE index operation SHALL be wrapped in a single transaction so that a crash mid-index leaves no partial data.
4. THE index operation SHALL NOT block the main analysis pipeline — if SQLite is temporarily locked (e.g., another session is writing), it SHALL retry up to 3 times with 100ms backoff, then log a warning and skip (the migration script can catch it later).
5. THE `index_analysis()` function SHALL be idempotent — calling it twice with the same file produces the same database state.

---

### Requirement 3: Dashboard Read Functions (Replace Filesystem Scanning)

**User Story:** As a user, I want the History, Compare, and Chat views to load instantly regardless of how many past analyses I have, so that the app remains responsive as my data grows.

#### Acceptance Criteria

1. A NEW `list_analyses(ticker: str = None, date_from: str = None, date_to: str = None, rating: str = None, limit: int = 100, offset: int = 0) -> List[Dict]` function SHALL be added to `dashboard/db.py` that queries the `analyses` table with optional filters.
2. THE `list_analyses()` function SHALL return lightweight dicts (no report text) suitable for rendering summary tables.
3. A NEW `get_analysis_reports(analysis_id: int) -> Dict[str, str]` function SHALL return all report text for a single analysis (loaded on drill-in).
4. THE existing `list_history()` function in `dashboard/utils.py` SHALL be refactored to call `list_analyses()` internally when the DataStore exists, falling back to filesystem scanning only when the database is absent (backward compatibility during migration).
5. THE existing `list_history_summary()` function SHALL be replaced by `list_analyses()` — they serve the same purpose but SQLite is faster and uses no in-memory caching.
6. THE `@st.cache_data(ttl=30)` decorator on `list_history()` SHALL be removed when using the SQLite path — SQLite queries are fast enough (<10ms for 1000 records) that caching adds complexity without benefit.
7. THE `load_run(json_file)` function SHALL remain available for loading the raw JSON file directly (used by Chat context building where the full unstructured state is needed).

---

### Requirement 4: Memory Log SQLite Integration

**User Story:** As a developer, I want the memory log to be queryable via SQL so that features like "filter by return > 5%" and "show all pending entries" are instant.

#### Acceptance Criteria

1. THE `TradingMemoryLog.store_decision()` method SHALL INSERT into the `memory_entries` table in addition to writing the markdown file (dual-write).
2. THE `TradingMemoryLog.batch_update_with_outcomes()` method SHALL UPDATE the corresponding `memory_entries` rows (setting `raw_return`, `alpha_return`, `holding_days`, `reflection`, `pending=0`) in addition to updating the markdown file.
3. A NEW `load_memory_entries_db(ticker: str = None, pending_only: bool = False) -> List[Dict]` function SHALL be added to `dashboard/db.py` that queries the `memory_entries` table.
4. THE existing `load_memory_entries()` function in `dashboard/utils.py` SHALL call `load_memory_entries_db()` when the DataStore exists, falling back to markdown parsing when it does not.
5. THE `get_pending_entries()` method on `TradingMemoryLog` SHALL query SQLite (`WHERE pending = 1 AND ticker = ?`) instead of scanning the full markdown file, when the DataStore exists.

---

### Requirement 5: Chat History SQLite Integration

**User Story:** As a user, I want my chat history to be stored in a queryable database so that features like "multi-analysis badge" and "resume previous chat" are instant without scanning files.

#### Acceptance Criteria

1. THE Chat view SHALL INSERT each new message into the `chat_messages` table with the appropriate `conversation_id`, `analysis_ticker`, `analysis_date`, `mode`, and `role`.
2. THE Chat view SHALL load conversation history from `chat_messages` WHERE `conversation_id = ?` ORDER BY `created_at ASC`.
3. THE multi-analysis badge computation SHALL use a single SQL query: `SELECT DISTINCT analysis_ticker, analysis_date FROM chat_messages WHERE mode = 'multi'` — no file scanning needed.
4. THE existing JSON-based chat history files SHALL continue to be written for portability (dual-write), but reads SHALL come from SQLite.
5. A NEW `conversation_id` SHALL be generated as `{mode}_{ticker}_{date}_{uuid4_short}` to uniquely identify each chat session.

---

### Requirement 6: Portfolio Positions SQLite Integration

**User Story:** As a user, I want my portfolio positions stored in the same database as my analyses so that joins (e.g., "show last analysis for each position") are instant.

#### Acceptance Criteria

1. THE Portfolio view SHALL CRUD positions via `dashboard/db.py` functions: `add_position(ticker, shares, cost_basis)`, `update_position(ticker, shares)`, `remove_position(ticker)`, `list_positions() -> List[Dict]`.
2. THE `list_positions()` function SHALL JOIN with `analyses` to include the most recent analysis date and rating for each position (if available): `LEFT JOIN analyses ON portfolio_positions.ticker = analyses.ticker ORDER BY analyses.trade_date DESC LIMIT 1 per ticker`.
3. THE portfolio JSON file (`~/.tradingagents/portfolio/portfolio.json`) SHALL continue to be written as a backup (dual-write), but reads SHALL come from SQLite.
4. THE atomic write pattern (with NTFS retry) SHALL still apply to the JSON backup file.

---

### Requirement 7: One-Time Migration Script

**User Story:** As an existing user with hundreds of saved analyses, I want all my historical data automatically imported into the new database on first run, so that I don't lose any history.

#### Acceptance Criteria

1. A NEW `dashboard/migrate_to_sqlite.py` script SHALL scan all existing `full_states_log_*.json` files under `~/.tradingagents/logs/` and call `index_analysis()` for each.
2. THE migration script SHALL parse the existing `trading_memory.md` (or `trading_memory.json` if it exists from the memory-log-json-migration spec) and INSERT all entries into `memory_entries`.
3. THE migration script SHALL parse existing chat history JSON files and INSERT messages into `chat_messages`.
4. THE migration script SHALL be idempotent — running it multiple times produces the same database state (uses INSERT OR REPLACE / INSERT OR IGNORE).
5. THE migration script SHALL report progress: `"Migrating analyses... {N}/{total} ({percent}%)"`.
6. THE migration script SHALL be triggered automatically on first dashboard launch when the DataStore does not exist but JSON files do exist. It SHALL display a one-time Streamlit info banner: "🔄 Migrating historical data to database... This happens once and takes about {estimated_seconds} seconds."
7. THE migration SHALL run in a background thread so the dashboard remains responsive during migration. Queries against the database during migration SHALL return partial results (whatever has been indexed so far).
8. WHEN the migration completes, THE script SHALL record the completion in `schema_version` table and SHALL NOT run again on subsequent launches.

---

### Requirement 8: Schema Migration Support

**User Story:** As a developer, I want to evolve the database schema over time without breaking existing installations.

#### Acceptance Criteria

1. THE `get_db()` function SHALL check the current `schema_version` on every connection and apply any pending migrations sequentially.
2. Migrations SHALL be defined as numbered Python functions in `dashboard/db.py`: `_migrate_v1_to_v2()`, `_migrate_v2_to_v3()`, etc.
3. Each migration function SHALL run inside a transaction — if it fails, the database remains at the previous version.
4. THE current schema (as defined in Requirement 1) SHALL be version 1.
5. WHEN a migration adds a new column, it SHALL use `ALTER TABLE ... ADD COLUMN` with a default value so existing rows are valid.

---

### Requirement 9: Backward Compatibility and Graceful Degradation

**User Story:** As a user, I want the dashboard to work even if the SQLite database is corrupted or deleted, falling back to the original filesystem-based approach.

#### Acceptance Criteria

1. WHEN the DataStore file is missing or corrupted (fails to open), ALL dashboard read functions SHALL fall back to the original filesystem-scanning approach and log a warning.
2. WHEN the DataStore is recreated (e.g., user deletes the .db file), the auto-migration (Requirement 7 AC 6) SHALL re-trigger on next launch.
3. THE original JSON files SHALL NEVER be deleted by the SQLite layer — they remain the source of truth and the database is a derived index.
4. THE `dashboard/db.py` module SHALL expose a `is_db_available() -> bool` function that other modules use to decide whether to use SQLite or filesystem fallback.
5. WHEN SQLite queries fail at runtime (e.g., disk full, locked), the affected function SHALL fall back to filesystem scanning for that call and log a warning — the dashboard SHALL NOT crash.

---

### Requirement 10: Performance Targets

**User Story:** As a user, I want the dashboard to feel instant regardless of how many analyses I've accumulated.

#### Acceptance Criteria

1. THE `list_analyses()` query SHALL complete in under 50ms for up to 5,000 analysis records.
2. THE `get_analysis_reports(analysis_id)` query SHALL complete in under 10ms (single row lookup by primary key).
3. THE `load_memory_entries_db()` query SHALL complete in under 20ms for up to 10,000 memory entries.
4. THE database file size SHALL be approximately 50-70% of the total JSON file size (SQLite compression + no duplicate metadata).
5. WAL mode SHALL be enabled to allow concurrent reads during writes (important during migration and during active analysis runs).
6. THE `get_db()` function SHALL set `journal_mode=WAL`, `synchronous=NORMAL`, and `cache_size=-64000` (64MB cache) for optimal read performance.

---

### Requirement 11: Data Integrity

**User Story:** As a user, I want confidence that my data is never lost or corrupted, even if the app crashes mid-operation.

#### Acceptance Criteria

1. ALL write operations (index, memory update, chat insert, portfolio CRUD) SHALL be wrapped in explicit transactions.
2. THE DataStore SHALL use `synchronous=NORMAL` (not OFF) to ensure data survives application crashes (though not OS crashes — acceptable tradeoff for performance).
3. WHEN the pipeline saves a JSON file but the index hook fails, THE JSON file SHALL still be saved successfully — the index can be rebuilt later via the migration script.
4. THE migration script SHALL verify data integrity after completion by comparing the count of `analyses` rows against the count of JSON files found on disk. A mismatch SHALL be logged as a warning.
5. THE `reports` table SHALL use `ON DELETE CASCADE` so that deleting an analysis record automatically removes its reports — no orphaned data.
