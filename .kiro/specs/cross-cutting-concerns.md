# Cross-Cutting Concerns

This document captures shared infrastructure, dependency ordering, and architectural decisions that span multiple specs. It serves as the implementation roadmap.

---

## Dependency Graph

```
Phase 1A: Foundation — Pipeline (no dependencies)
├── Parallel Analyst Execution (graph/setup.py change)
└── Bug Fixes (2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17)

Phase 1B: Foundation — Data Layer (no dependencies, parallel with 1A)
├── SQLite Data Layer (schema, migration, read functions)
├── Memory JSON Migration (dual-write to SQLite + markdown)
└── Shared Utilities (compute_conviction, render_decision_first, list_history_summary)

Phase 2: Core UX (depends on Phase 1A + 1B)
├── Single Ticker UX Improvements
├── History UX Improvements
└── Compare UX Improvements

Phase 3: Parallel Infrastructure (depends on Phase 1A + 1B)
├── Multi-Ticker Analysis (rename + parallel pool + new features)
└── run_analysis() portfolio_context parameter

Phase 4: Advanced Features (depends on Phases 2 + 3)
├── Analysis Chat Multi-Mode
└── Portfolio Management

Phase 5: Deferred
└── Multi-Ticker Batch Presets (Req 3d)
```

### Detailed Dependencies

| Spec | Depends On |
|------|-----------|
| Parallel Analyst Execution | None (pipeline-internal) |
| SQLite Data Layer | None |
| Memory JSON Migration | SQLite Data Layer (writes to SQLite) |
| Bug Fixes | None |
| Shared Utilities | Bug Fix 14, SQLite Data Layer (list_analyses replaces list_history_summary) |
| Single Ticker UX | Bug 4, Bug 17, compute_conviction, Parallel Analyst Execution (progress tracking) |
| History UX | SQLite Data Layer, Bug 6, compute_conviction |
| Compare UX | compute_conviction |
| Multi-Ticker Analysis | Bug 2, Bug 3, Bug 4, Bug 17, compute_conviction |
| Analysis Chat | Bug 9, SQLite Data Layer (chat_messages table) |
| Portfolio Management | SQLite Data Layer, Multi-Ticker Worker_Pool, compute_conviction, render_decision_first, run_analysis portfolio_context |

---

## Shared Utilities to Extract

### 1. `compute_conviction(reports: dict) -> tuple[str, str]`

**Location:** `dashboard/utils.py`
**Source:** Currently `_conviction()` in `dashboard/views/single_ticker.py`
**Consumers:** Single Ticker, Compare, History, Portfolio, Multi-Ticker

Logic: Count how many of the 7 report sections (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`, `investment_plan`, `trader_investment_plan`, `final_trade_decision`) are non-empty strings. Return `("High", "#22c55e")` if score ≥ 6, `("Medium", "#f59e0b")` if score ≥ 4, else `("Low", "#ef4444")`.

### 2. `render_decision_first(data: dict, container) -> None`

**Location:** `dashboard/utils.py`
**Consumers:** Single Ticker, History (run detail panel), Portfolio (individual analysis), Multi-Ticker (expanded result)

Renders the decision-first layout into a given Streamlit container:
1. Decision Banner (colored rating)
2. Key Metrics Row (Price Target, Time Horizon, Conviction)
3. Executive Summary (inline, no expander)
4. Analyst report expanders (collapsed)
5. Pipeline expanders (Research Plan, Trader Plan, Final Decision — Final expanded by default)

This function encapsulates:
- Regex extraction of Price Target, Time Horizon, Executive Summary (case-insensitive)
- HTML escaping of extracted values (Bug 16 fix)
- Trader plan key fallback (Bug 5 fix)
- `sanitize_report()` applied to all report text
- `compute_conviction()` call for the metrics row

### 3. `list_history_summary() -> List[Dict]`

**Location:** `dashboard/utils.py`
**Source:** New function (Bug 14 fix)
**Consumers:** History view summary table, Portfolio Overview last-analysis join

Returns lightweight records (ticker, date, rating, file path, portfolio_context) without full report text. Cached with 30s TTL.

### 4. `Worker_Pool` (extracted module)

**Location:** `dashboard/worker_pool.py`
**Source:** Currently embedded in `dashboard/views/watchlist.py`
**Consumers:** Multi-Ticker Analysis view, Portfolio batch analysis

Provides:
- Session-scoped results buffer (Bug 3 fix)
- Thread-safe dispatch of up to N concurrent analyses
- Main-thread drain cycle
- Cancel/skip support per worker
- Progress tracking per active worker

Interface:
```python
class WorkerPool:
    def __init__(self, session_id: str, max_concurrency: int = 3): ...
    def dispatch(self, ticker: str, date: str, analysts: list, config: dict,
                 portfolio_context: str | None = None, prior_run: dict | None = None): ...
    def drain_results(self) -> List[Dict]: ...
    def cancel(self, ticker: str): ...
    def cancel_all(): ...
    def active_count(self) -> int: ...
    def active_tickers(self) -> Dict[str, RunState]: ...
```

### 5. `invalidate_history_cache()`

**Location:** `dashboard/utils.py` (already exists)
**Note:** Must be called per-result when "Open in Chat" is clicked during an active batch (Bug 8 fix), not only at batch completion. When SQLite is active, this function becomes a no-op (SQLite reads are always fresh).

### 6. `dashboard/db.py` (SQLite Data Layer)

**Location:** `dashboard/db.py` (new module)
**Consumers:** All dashboard views, runner (post-save hook), memory log

Provides:
- `get_db() -> sqlite3.Connection` — thread-local cached connection with WAL mode
- `is_db_available() -> bool` — check if SQLite is usable
- `index_analysis(json_path, data)` — post-save hook to index a completed analysis
- `list_analyses(ticker, date_from, date_to, rating, limit, offset)` — replaces `list_history_summary()`
- `get_analysis_reports(analysis_id)` — load full reports on drill-in
- `load_memory_entries_db(ticker, pending_only)` — replaces markdown parsing
- Portfolio CRUD: `add_position()`, `update_position()`, `remove_position()`, `list_positions()`
- Chat: `save_chat_message()`, `load_conversation()`, `list_multi_chat_analyses()`

---

## Implementation Order (Recommended)

### Sprint 1A: Pipeline Foundation (can run in parallel with 1B)
1. Parallel Analyst Execution — modify `setup_graph()` for fan-out/barrier pattern
2. Add `"parallel_analysts": True` to DEFAULT_CONFIG
3. Update `_build_fast_graph()` for parallel pattern
4. Add error handling in parallel branches (warnings on failure)
5. Update progress tracking callbacks for parallel status

### Sprint 1B: Data + Bug Foundation (can run in parallel with 1A)
1. Bug 4 — RunState `start()` method
2. Bug 2 — Remove session state access from background threads
3. Bug 3 — Session-scoped results buffer
4. Bug 5 — Trader plan key fallback (all views)
5. Bug 6 — History deduplication
6. Bug 15 — sanitize_report() allowlist
7. Bug 16 — HTML escaping for extracted values
8. Bug 11 — safe_ticker_component whitespace rejection
9. Bug 12 — Delete broken test file
10. SQLite Data Layer — schema, `get_db()`, `index_analysis()`, `list_analyses()`, `get_analysis_reports()`
11. Migration script (`dashboard/migrate_to_sqlite.py`)
12. Memory log dual-write to SQLite (replaces memory-log-json-migration read path)

### Sprint 2: Shared Utilities + Quick Fixes
1. Extract `compute_conviction()` to utils.py
2. Bug 7 — Chat prefill fallback fix
3. Bug 8 — Per-result cache invalidation
4. Bug 9 — Context window overflow protection
5. Bug 10 — "Run Again" date prefill
6. Bug 13 — Per-ticker date validation warning
7. Bug 17 — time.sleep replacement (with streamlit-autorefresh middle fallback)
8. Build `render_decision_first()` shared utility
9. Implement `list_history_summary()` as thin wrapper over SQLite/filesystem
10. Update single_ticker.py to use `render_decision_first()` for completed results

### Sprint 3: UX Improvements
1. Single Ticker UX (progress bar, parallel timeline, live log, decision-first layout, ticker validation)
2. History UX (decision-first detail, ticker search, date filter, return filter — all via SQLite queries)
3. Compare UX (expanders, ticker filter, comparison table, "Compare both in Chat", executive summary)

### Sprint 4: Parallel Infrastructure
1. Extract Worker_Pool to `dashboard/worker_pool.py`
2. Multi-Ticker Analysis rename + parallel pool (Req 1, 7, 9)
3. Multi-Ticker new features (Import from Portfolio, Skip, Chart, Chat shortcut, Fast Mode)
4. `run_analysis()` portfolio_context parameter (Portfolio Req 14)

### Sprint 5: Advanced Features
1. Analysis Chat Multi-Mode (all requirements)
2. Portfolio Management (all requirements)

---

## Architectural Decisions

### AD-1: No concurrent runs across views
A user cannot run a Single Ticker analysis AND a Portfolio batch simultaneously. Each view checks if any other view has an active run via a shared `st.session_state["_global_run_active"]` flag. If active, the Run button is disabled with a message: "Another analysis is running. Wait for it to complete or cancel it."

### AD-2: Worker_Pool is a shared module, not embedded in a view
The parallel execution infrastructure lives in `dashboard/worker_pool.py` and is imported by both `watchlist.py` and `portfolio.py`. This prevents code duplication and ensures both views benefit from bug fixes.

### AD-3: Decision-first layout is a shared function
The `render_decision_first()` function in `dashboard/utils.py` is called by 4+ views. Changes to the layout (e.g., adding a new metric) only need to happen in one place.

### AD-4: Atomic writes with NTFS fallback
All JSON persistence (portfolio, memory log, chat history) uses the atomic write pattern (write to .tmp, rename). On NTFS/WSL where rename can fail due to file locking, a retry + direct-write fallback is used. This is documented in portfolio-management Req 2 AC 8 and applies to all atomic write sites.

### AD-5: Streamlit version compatibility
The project targets Streamlit ≥ 1.33 for `st.fragment` with `run_every`. If running on an older version, the `time.sleep` pattern is retained with a logged warning. Version detection happens at import time in a module-level check.

### AD-6: SQLite is a derived index, not the source of truth
The JSON files written by the pipeline remain the authoritative data. SQLite is a read-optimized index that can be rebuilt at any time by re-running the migration script. If the database is deleted or corrupted, the dashboard falls back to filesystem scanning. This means we never lose data — only read performance degrades temporarily.

### AD-7: Analysts execute in parallel by default
The LangGraph pipeline fans out from START to all selected analysts simultaneously, converging at a barrier node before the Research Debate. Each analyst writes to an independent state field, so no locking is needed. A `parallel_analysts: False` config option exists for debugging. This reduces the analyst phase from 60-120s to 20-40s.

### AD-8: Dual-write pattern for all persistence
All write operations write to both the original format (JSON/markdown) AND SQLite. This ensures:
- Portability: users can copy JSON files to another machine
- Recoverability: SQLite can always be rebuilt from JSON
- Backward compatibility: older versions of the app still work with JSON files

---

## Files Modified by Multiple Specs

| File | Specs That Modify It |
|------|---------------------|
| `dashboard/db.py` | SQLite Data Layer (new), Memory Migration, History UX, Chat, Portfolio |
| `dashboard/utils.py` | Bug Fixes, Memory Migration, History UX, All (shared utilities) |
| `dashboard/runner.py` | Bug Fixes (4), SQLite (post-save hook), Portfolio (14) |
| `dashboard/views/watchlist.py` | Bug Fixes (2, 3, 5, 8, 13, 17), Multi-Ticker Analysis |
| `dashboard/views/single_ticker.py` | Bug Fixes (16, 17), Single Ticker UX, History UX (Req 9 extraction) |
| `dashboard/views/history.py` | Bug Fixes (5, 10), History UX |
| `dashboard/views/compare.py` | Bug Fixes (5), Compare UX |
| `dashboard/views/chat.py` | Bug Fixes (7, 9), Analysis Chat, SQLite (chat persistence) |
| `streamlit_app.py` | Multi-Ticker (rename), Portfolio (new nav entry), SQLite (migration banner) |
| `tradingagents/graph/setup.py` | Parallel Analyst Execution |
| `tradingagents/agents/utils/memory.py` | Memory JSON Migration, SQLite (dual-write) |
| `tradingagents/dataflows/utils.py` | Bug Fix 11 |
| `tradingagents/default_config.py` | Parallel Analyst Execution (parallel_analysts key) |

---

## Testing Strategy

Each sprint should include:
1. **Unit tests** for shared utilities (`compute_conviction`, `sanitize_report`, `WorkerPool`)
2. **Integration tests** for persistence (SQLite CRUD, migration script, memory dual-write)
3. **Pipeline tests** for parallel analyst execution (verify all reports populated, error handling)
4. **Manual smoke tests** for UI changes (Streamlit views can't be easily unit-tested)
5. **Regression** — run existing test suite after each sprint to catch breakage

Priority test targets:
- `setup_graph()` parallel vs sequential produces identical `final_state` (Parallel Analyst Execution Req 8)
- Analyst failure isolation (one fails, others complete — Req 6)
- SQLite `index_analysis()` idempotency (call twice, same result)
- SQLite migration script (empty DB, partial migration, re-run)
- SQLite fallback to filesystem when DB unavailable
- `WorkerPool` thread safety (concurrent dispatch, drain, cancel)
- `sanitize_report()` allowlist (legitimate HTML preserved, tool_calls stripped)
- `render_decision_first()` with missing fields (no price target, no executive summary, no final_trade_decision)
