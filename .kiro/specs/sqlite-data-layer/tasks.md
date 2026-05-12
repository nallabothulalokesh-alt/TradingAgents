# Tasks — Sprint 1B: SQLite Data Layer + Bug Fixes + Memory Migration

## Bug Fixes — Thread Safety

### Task 1: RunState `start()` method (Bug 4)
- [ ] Add `start(ticker, trade_date, agent_status)` method to `RunState` in `dashboard/utils.py`
- [ ] Method acquires `self._lock` and sets all 4 fields atomically
- [ ] In `dashboard/runner.py` `run_analysis()`, replace direct assignments (lines 285-292) with `run_state.start(...)`
- [ ] Remove redundant assignments in `_worker()` (lines 298-304)
- [ ] Keep `run_state.append_log()` call before thread start (outside `start()`)
- [ ] Test: verify `snapshot()` returns consistent state immediately after `start()`

### Task 2: Verify no session_state access from threads (Bug 2)
- [ ] Audit `_worker()` in `watchlist.py` — confirm no `st.session_state` access
- [ ] Audit `run_analysis._worker()` in `runner.py` — confirm no `st.session_state` access
- [ ] Add code comment at top of each `_worker()`: "# THREAD SAFETY: This runs on a background thread. Do NOT access st.session_state."
- [ ] Verify `_dispatch_next()` is only called from main thread (in `_drain_results_and_advance()`)

### Task 3: Session-scoped results buffer (Bug 3)
- [ ] **MINIMAL FIX** (will be superseded by WorkerPool in Sprint 4): Add session_id key to buffer access
- [ ] Replace `_results_buffer: List` with `_results_buffers: Dict[str, List] = {}`
- [ ] In `_init_wl()`, generate `st.session_state["_wl_session_id"] = str(uuid4())` if not present
- [ ] In `_worker()`, write to `_results_buffers[session_id]` (pass session_id at dispatch)
- [ ] In `_drain_results_and_advance()`, drain only from own session's buffer
- [ ] **NOTE:** Skip the cleanup logic (stale buffer removal) — WorkerPool in Sprint 4 replaces this entire mechanism. Keep the fix minimal to unblock multi-user safety without over-engineering throwaway code.
- [ ] Test: two sessions don't see each other's results

## Bug Fixes — Data Integrity

### Task 4: Trader plan key fallback (Bug 5)
- [ ] In `dashboard/views/history.py` `_render_run_detail()`: use `data.get("trader_investment_decision") or data.get("trader_investment_plan")`
- [ ] In `dashboard/views/compare.py` `_render_side()`: same fallback
- [ ] In `dashboard/views/watchlist.py` results expander: same fallback
- [ ] Test: load a pre-rename analysis file, verify trader plan renders

### Task 5: History deduplication (Bug 6)
- [ ] In `dashboard/utils.py` `list_history()`, after scanning all files:
  - Group records by `(ticker, date)`
  - For duplicates, keep only the record with the newest file mtime
- [ ] Test: create two files for same ticker+date, verify only newest appears

### Task 6: sanitize_report() allowlist (Bug 15)
- [ ] Define `_ALLOWED_TAGS` set at module level in `dashboard/utils.py`
- [ ] Rewrite `sanitize_report()` to: strip tool_calls/script → strip non-allowlisted tags (keep content) → collapse whitespace
- [ ] Remove the duplicate `<tool_calls>` regex
- [ ] Test: `<b>bold</b>` preserved, `<tool_calls>...</tool_calls>` removed, `<script>...</script>` removed, `<custom>text</custom>` → `text`

### Task 7: HTML escaping (Bug 16)
- [ ] In `dashboard/views/single_ticker.py` `_render_reports()`: wrap `price_target`, `time_horizon`, `exec_summary` with `html.escape()`
- [ ] Add `import html` at top of file
- [ ] Test: LLM output containing `<script>` in price target is escaped, not executed

### Task 8: safe_ticker_component whitespace (Bug 11)
- [ ] In `tradingagents/dataflows/utils.py` `safe_ticker_component()`: add whitespace check BEFORE `.strip()`
- [ ] `if any(c in value for c in ' \t\n\r'): raise ValueError(...)`
- [ ] Test: `"AAP L"` raises ValueError, `"AAPL"` passes

### Task 9: Delete broken test (Bug 12)
- [ ] Delete `tests/test_ticker_symbol_handling.py`
- [ ] Run `pytest --collect-only` to verify no collection errors

## SQLite Data Layer

### Task 10: Create `dashboard/db.py` module
- [ ] Implement `get_db()` with thread-local connection, WAL mode, foreign keys
- [ ] Implement `_ensure_schema(conn)` creating all tables + indexes from spec
- [ ] Implement `is_db_available() -> bool`
- [ ] Implement `close_db()` for cleanup
- [ ] Test: `get_db()` creates DB file, tables exist, WAL mode active

### Task 11: Implement `index_analysis(json_path, data, conviction=None)`
- [ ] Accept optional `conviction` parameter (computed by caller to avoid circular import with utils.py)
- [ ] Extract: ticker, trade_date, rating (via inline regex — do NOT import from utils), executive_summary, price_target, time_horizon
- [ ] If `conviction` not provided: compute inline (count non-empty report fields, same logic as `compute_conviction()`)
- [ ] INSERT OR REPLACE into `analyses` table
- [ ] INSERT OR REPLACE each report section into `reports` table
- [ ] Wrap in single transaction
- [ ] Retry up to 3 times on SQLITE_BUSY with 100ms backoff
- [ ] **IMPORTANT:** `db.py` must NOT import from `dashboard/utils.py` (circular import risk). Use inline logic or accept pre-computed values as parameters.
- [ ] Test: index same file twice → same DB state (idempotent)

### Task 12: Implement `list_analyses()` query function
- [ ] `list_analyses(ticker=None, date_from=None, date_to=None, rating=None, limit=100, offset=0) -> List[Dict]`
- [ ] Build SQL dynamically based on provided filters
- [ ] Return lightweight dicts (no report text)
- [ ] Test: insert 100 records, query with filters, verify correct results

### Task 13: Implement `get_analysis_reports(analysis_id)`
- [ ] Query `reports` table WHERE `analysis_id = ?`
- [ ] Return `{report_type: content}` dict
- [ ] Test: insert analysis + reports, retrieve by ID, verify all sections present

### Task 14: Add post-save hook in runner.py
- [ ] After `graph_obj._log_state(trade_date, final_state)` in `_worker()`:
  - Call `from dashboard.db import index_analysis, is_db_available`
  - If `is_db_available()`: call `index_analysis(log_path, state_dict)`
- [ ] Wrap in try/except — never let indexing failure crash the pipeline
- [ ] Test: run analysis, verify record appears in SQLite

### Task 15: Implement migration script
- [ ] Create `dashboard/migrate_to_sqlite.py` with `run_migration()` function
- [ ] Scan all `full_states_log_*.json` files under RESULTS_DIR
- [ ] Call `index_analysis()` for each (with progress logging)
- [ ] Parse `trading_memory.md` and INSERT into `memory_entries` table
- [ ] Record completion in `schema_version` table
- [ ] Make idempotent (INSERT OR REPLACE)
- [ ] Test: run migration twice, verify same DB state

### Task 16: Auto-trigger migration on first launch
- [ ] In `streamlit_app.py` or `dashboard/utils.py` startup:
  - If DB doesn't exist but JSON files do → spawn migration in background thread
  - Show one-time info banner: "🔄 Migrating historical data..."
- [ ] Migration thread sets a session_state flag when complete
- [ ] Test: delete DB, restart app, verify migration runs and banner shows

## Memory Migration

### Task 17: Add SQLite dual-write to TradingMemoryLog
- [ ] Add `sqlite_db_path` to config handling in `TradingMemoryLog.__init__()`
- [ ] In `store_decision()`: after markdown write, INSERT into `memory_entries` (pending=1)
- [ ] In `batch_update_with_outcomes()`: after markdown update, UPDATE `memory_entries` rows
- [ ] Test: store decision, verify both markdown and SQLite have the entry

### Task 18: Implement `load_memory_entries_db()`
- [ ] In `dashboard/db.py`: query `memory_entries` table with optional ticker/pending filters
- [ ] In `dashboard/utils.py` `load_memory_entries()`: use SQLite when available, fall back to markdown
- [ ] Test: load entries from SQLite, verify same data as markdown parser

### Task 19: Schema migration support
- [ ] In `_ensure_schema()`: check `schema_version` table, apply pending migrations
- [ ] Define `_MIGRATIONS = {2: _migrate_v1_to_v2, ...}` (empty for now)
- [ ] Each migration runs in a transaction
- [ ] Test: manually set version=0, verify schema is recreated

## Integration Tests

### Task 20: End-to-end verification
- [ ] Run full analysis pipeline → verify JSON saved AND SQLite indexed
- [ ] Verify `list_analyses()` returns the new record
- [ ] Verify `load_memory_entries()` returns from SQLite (not markdown)
- [ ] Verify `list_history()` still works (backward compat when DB unavailable)
- [ ] Delete DB file → verify app falls back to filesystem scanning gracefully
