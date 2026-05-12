# Requirements Document — Bug Fixes

## Introduction

This document captures all bugs identified during user journey analysis of the existing TradingAgents dashboard codebase. These bugs exist in the current code and must be fixed before or alongside the new feature specs. Each requirement corresponds to a specific bug with its root cause, affected file(s), and acceptance criteria for the fix.

**Implementation Priority:** These bugs MUST be fixed before feature work begins, as several features (Multi-Ticker parallel pool, Portfolio batch analysis) depend on thread-safety fixes (Bugs 2, 3, 4) being in place.

---

## Glossary

- **RunState**: Thread-safe container class in `dashboard/utils.py` tracking a live analysis run.
- **Worker_Pool**: The background thread execution model in `dashboard/views/watchlist.py`.
- **Fast Mode**: The analysis mode in `dashboard/runner.py` that reuses prior fundamentals and research plan.
- **GraphSetup**: The class in `tradingagents/graph/setup.py` that builds the LangGraph agent pipeline.
- **_results_buffer**: Module-level list in `watchlist.py` used by background threads to pass results to the main thread.
- **safe_ticker_component**: Ticker validation function in `tradingagents/dataflows/utils.py`.
- **HTML_ALLOWLIST**: The set of HTML tags considered safe for rendering in reports: `<b>, <i>, <em>, <strong>, <table>, <tr>, <td>, <th>, <ul>, <ol>, <li>, <p>, <br>, <h1>-<h6>, <blockquote>, <code>, <pre>, <span>, <div>, <a>, <hr>`.

---

## Requirements

### Bug 1: Fast Mode Graph Does Not Skip Research Team

**Severity:** CRITICAL
**Status:** ✅ RESOLVED — verified in current `dashboard/runner.py`
**File:** `dashboard/runner.py` — `_build_fast_graph()` function
**Root Cause:** Originally, `_build_fast_graph()` called `fast_setup.setup_graph(fast_analysts)` which ALWAYS builds the full pipeline. This has been fixed — the function now builds the graph manually.

#### Acceptance Criteria

1. THE `_build_fast_graph()` function SHALL build a custom `StateGraph` that does NOT include Bull Researcher, Bear Researcher, or Research Manager nodes.
2. THE Fast Mode graph SHALL connect the last analyst's "Msg Clear" node directly to the Trader node, bypassing the research debate.
3. THE pre-seeded `investment_plan` in the initial state SHALL be preserved through graph execution — no node SHALL overwrite it.
4. THE Fast Mode graph SHALL include: selected analyst nodes (market, news, social if selected), Trader, Risk Team (Aggressive/Conservative/Neutral), and Portfolio Manager.
5. THE `_build_fast_graph()` function SHALL NOT call `GraphSetup.setup_graph()`.
6. WHEN Fast Mode completes, the saved JSON SHALL contain both the reused `fundamentals_report` and `investment_plan` alongside the fresh reports from the agents that ran.

**Verification:** A unit test SHALL confirm that running `_build_fast_graph()` produces a graph whose node set does not include "Bull Researcher", "Bear Researcher", or "Research Manager".

---

### Bug 2: Watchlist Background Thread Accesses Session State

**Severity:** CRITICAL
**File:** `dashboard/views/watchlist.py` — `_start_next()` called from `_on_done()` inside `_worker()` thread
**Root Cause:** `_on_done()` runs on a background thread and calls `_start_next()` which reads/writes `st.session_state["wl_queue"]`, `st.session_state["wl_running"]`, and `st.session_state["wl_current"]`. Streamlit session state is NOT thread-safe — accessing it from a non-main thread causes `RuntimeError` or silent corruption.

#### Acceptance Criteria

1. Background threads SHALL only write to the module-level `_results_buffer` (protected by `_results_lock`).
2. Background threads SHALL NOT read or write `st.session_state` in any code path.
3. The `_on_done()` function SHALL NOT call `_start_next()`. Instead, it SHALL append the result to `_results_buffer` and return.
4. The main Streamlit thread SHALL handle queue advancement: at the start of each render cycle, drain `_results_buffer`, check if the current run is done, and if so, start the next queued item.
5. THE fix SHALL preserve the existing sequential execution model (one ticker at a time) until the parallel Worker_Pool feature is implemented.

**Note:** The current `_worker()` in watchlist.py calls `run_analysis()` which spawns its own background thread, making `_worker()` a wrapper that waits. This double-threading is acceptable for now — the parallel Worker_Pool (multi-ticker-analysis spec Req 7) will flatten this.

---

### Bug 3: Module-Level _results_buffer Shared Across Sessions

**Severity:** HIGH
**File:** `dashboard/views/watchlist.py` — lines 18-19
**Root Cause:** `_results_buffer` and `_results_lock` are module-level variables. In Streamlit's architecture, module-level state is shared across ALL user sessions. If two users run watchlist batches simultaneously, results from one user's background threads are drained by the other user's render cycle.

#### Acceptance Criteria

1. THE `_results_buffer` SHALL be scoped per-session. Each session SHALL have its own buffer that only its background threads write to and only its main thread drains.
2. THE implementation SHALL use a session-keyed dict at module level: `_results_buffers: Dict[str, List] = {}` where the key is a unique session identifier stored in `st.session_state["_wl_session_id"]` (generated once via `uuid4()` on first access).
3. Background threads SHALL receive the session ID at dispatch time and write to the correct buffer.
4. THE main thread SHALL only drain its own session's buffer.
5. Stale buffer cleanup SHALL occur during the main thread's drain cycle: WHEN draining its own buffer, THE main thread SHALL also check all other buffer keys and remove any whose `_last_access` timestamp is older than 1 hour AND whose buffer list is empty. A `_last_access` timestamp SHALL be updated each time a buffer is written to or drained.
6. THE cleanup SHALL NOT remove buffers that still contain unread results, regardless of age, to prevent data loss from slow-draining sessions.

---

### Bug 4: RunState Attributes Set Without Lock

**Severity:** HIGH
**File:** `dashboard/runner.py` — `run_analysis()` lines ~285-292 and `_worker()` lines ~298-304
**Root Cause:** `running`, `ticker`, `trade_date`, and `agent_status` are assigned directly on the RunState object without acquiring `self._lock`. The main thread's `snapshot()` could read partially-written state. Additionally, `_worker()` redundantly re-assigns these same fields.

#### Acceptance Criteria

1. THE `RunState` class SHALL expose a `start(ticker: str, trade_date: str, agent_status: dict)` method that sets `running=True`, `ticker`, `trade_date`, and `agent_status` atomically under `self._lock`.
2. THE `run_analysis()` function SHALL call `run_state.start(ticker, trade_date, agent_status)` instead of direct attribute assignment.
3. THE `_worker()` function SHALL NOT re-assign `running`, `ticker`, `trade_date`, or `agent_status` — these are set once before the thread starts.
4. ALL reads of `running`, `ticker`, `trade_date`, and `agent_status` from the main thread SHALL go through `snapshot()` which already acquires the lock.

---

### Bug 5: Trader Plan Key Name Fallback Missing

**Severity:** MEDIUM
**Files:** `dashboard/views/history.py` (line ~107), `dashboard/views/compare.py` (in `_render_side`), `dashboard/views/watchlist.py` (in results expander)
**Root Cause:** These views only check `data.get("trader_investment_plan")`. Analyses saved before the key was renamed use `trader_investment_decision`. The Trader Plan section appears empty for older analyses.

#### Acceptance Criteria

1. ALL views rendering the Trader Plan SHALL use the fallback expression: `data.get("trader_investment_decision") or data.get("trader_investment_plan")`.
2. THE fix SHALL be applied in:
   - `dashboard/views/history.py` — `_render_run_detail()` Trader Plan expander
   - `dashboard/views/compare.py` — `_render_side()` Trader section
   - `dashboard/views/watchlist.py` — expanded result detail section
3. No other code changes are required — the key name in `runner.py` (`_FIELD_TO_AGENT` mapping) uses `trader_investment_plan` which is the current standard.

---

### Bug 6: History Duplicate Entries for Same Ticker+Date

**Severity:** MEDIUM
**File:** `dashboard/utils.py` — `list_history()` function
**Root Cause:** `list_history()` iterates all `full_states_log_*.json` files and returns every one found. If a user runs the same ticker+date twice (e.g., re-runs NVDA on 2026-05-01), both files appear as separate rows in History.

#### Acceptance Criteria

1. THE `list_history()` function SHALL deduplicate records by `(ticker, date)` tuple.
2. WHEN duplicates exist for the same ticker+date, THE function SHALL keep only the record from the most recently modified file (by filesystem mtime).
3. THE function signature and return schema SHALL remain unchanged.
4. THE deduplication SHALL happen after all files are scanned but before the list is returned.

---

### Bug 7: Chat Prefill Silently Selects Wrong Analysis

**Severity:** MEDIUM
**File:** `dashboard/views/chat.py` — analysis selection logic
**Root Cause:** When navigating to Chat via "Open in Chat" from History/Watchlist, the code uses `next((i for i, r in enumerate(records) if ...), 0)`. If the target analysis isn't found (file deleted, cache stale), it silently falls back to index 0 — loading the wrong analysis with no warning.

#### Acceptance Criteria

1. WHEN `chat_prefill_ticker` and `chat_prefill_date` are set but no matching record is found in `list_history()`, THE Chat_View SHALL display an info message: "Analysis for {ticker} on {date} not found. It may have been deleted." and SHALL NOT auto-select any analysis.
2. THE fallback index SHALL be `None` (no selection) rather than `0` (first/most recent analysis).
3. WHEN no analysis is selected, THE Chat_View SHALL show the empty state with instructions to select an analysis from the dropdown.

---

### Bug 8: "Open in Chat" from Watchlist Fails During Active Batch

**Severity:** MEDIUM
**File:** `dashboard/views/watchlist.py` — "Open in Chat" button handler
**Root Cause:** `invalidate_history_cache()` is only called when the entire batch completes (inside `_start_next()` when queue is empty). If a user clicks "Open in Chat" on an early completed result while the batch is still running, the history cache doesn't include that result yet, so the Chat view can't find it.

#### Acceptance Criteria

1. WHEN the user clicks "💬 Open in Chat" on a completed Result, THE watchlist view SHALL call `invalidate_history_cache()` BEFORE setting `_nav_target` and calling `st.rerun()`.
2. This ensures the Chat view's `list_history()` call will re-scan the filesystem and find the newly saved analysis file.

---

### Bug 9: Chat Context Window Overflow

**Severity:** HIGH
**File:** `dashboard/views/chat.py` — `_stream_llm()` function
**Root Cause:** ALL chat history messages are sent to the LLM on every call with no truncation. The system prompt (analysis context) can be 15,000-30,000 tokens. Combined with 50+ messages of history, this exceeds context limits for smaller models (8K-64K), causing API errors that surface as "❌ LLM error: ..." in the chat.

#### Acceptance Criteria

1. THE `_stream_llm()` function SHALL estimate the total token count before sending (using words × 1.3 heuristic).
2. WHEN the estimated total exceeds 80% of the model's context window, THE function SHALL truncate the oldest history messages (keeping system prompt + most recent messages that fit).
3. THE Chat_View SHALL display a notice when messages are truncated: "ℹ️ Older messages were trimmed to fit the model's context window."
4. Model context window sizes SHALL be defined as: OpenAI gpt-4o/gpt-5.4 = 128K, DeepSeek = 64K, Anthropic Claude = 200K, Google Gemini = 1M, Ollama = 8K (default for unknown models = 8K).
5. WHEN the system prompt alone exceeds 80% of the model's context window (possible in Multi_Mode with 5+ analyses), THE `_stream_llm()` function SHALL truncate the system prompt by removing the oldest analysis contexts (keeping the preamble and the most recent analyses) and SHALL display a warning: "⚠️ Analysis context was trimmed to fit the model's context window. Consider selecting fewer analyses or using a model with a larger context window."
6. THE function SHALL never truncate the user's most recent message — it is always included regardless of token budget.

---

### Bug 10: "Run Again" from History Doesn't Prefill Date

**Severity:** LOW
**File:** `dashboard/views/history.py` — "Run Again" button handler (line ~60)
**Root Cause:** The button only sets `st.session_state["st_ticker_validated"] = record["ticker"]` but does not set the analysis date. The Single Ticker view defaults to `date.today()`, so re-running a historical analysis requires manually changing the date.

#### Acceptance Criteria

1. WHEN the user clicks "🔄 Run Again", THE History_View SHALL set `st.session_state["st_prefill_date"]` to the record's date string (YYYY-MM-DD).
2. THE Single_Ticker_View SHALL read `st.session_state.get("st_prefill_date")` and use it as the default for the date input widget.
3. THE Single_Ticker_View SHALL clear `st_prefill_date` from session state after consuming it (one-shot).
4. WHEN `st_prefill_date` is not set, THE date input SHALL default to `date.today()` (preserving current behavior).

---

### Bug 11: safe_ticker_component Test Failure

**Severity:** LOW
**File:** `tradingagents/dataflows/utils.py` — `safe_ticker_component()` function
**Root Cause:** The function normalizes whitespace (strips and removes spaces) instead of rejecting it. Test `test_rejects_null_byte_and_whitespace` expects `ValueError` for inputs like `"AAP L"`, `"AAPL\n"`, `"\tAAPL"` — but the function strips them to valid tickers. The design choice (normalize vs reject) is inconsistent with the test.

#### Acceptance Criteria

1. THE `safe_ticker_component()` function SHALL reject inputs containing whitespace characters (space, tab, newline, carriage return) with a `ValueError`, BEFORE normalization.
2. THE check SHALL be: `if any(c in value for c in ' \t\n\r'): raise ValueError(...)` applied to the raw input before `.strip()`.
3. THE existing test `test_rejects_null_byte_and_whitespace` SHALL pass without modification.
4. Callers that need normalization (e.g., the dashboard ticker input) SHALL strip whitespace BEFORE calling `safe_ticker_component()`.

---

### Bug 12: test_ticker_symbol_handling.py Imports Non-Existent Module

**Severity:** LOW
**File:** `tests/test_ticker_symbol_handling.py`
**Root Cause:** The test imports `from cli.utils import normalize_ticker_symbol` — the `cli` module was removed during a prior cleanup. This causes a collection error in pytest.

#### Acceptance Criteria

1. THE file `tests/test_ticker_symbol_handling.py` SHALL be deleted entirely, as the module it tests no longer exists.
2. IF the `normalize_ticker_symbol` functionality still exists elsewhere in the codebase, a new test SHALL be written that imports from the correct location.

---

### Bug 13: Per-Ticker Date Validation Silent Fallback

**Severity:** MEDIUM
**File:** `dashboard/views/watchlist.py` — ticker parsing in "Add to Queue" handler
**Root Cause:** When per-ticker date override is enabled and a user enters an invalid date (e.g., `NVDA 2026-13-45`), the code catches `ValueError` from `strptime` and silently falls back to the global date. No warning is shown to the user.

#### Acceptance Criteria

1. WHEN per-ticker date override is enabled and a date string cannot be parsed as `YYYY-MM-DD`, THE view SHALL display a per-line warning: `"{TICKER}: date '{entered_date}' is not valid (use YYYY-MM-DD format) — using global date instead."`
2. THE warning SHALL be displayed inline after the "Add to Queue" action using `st.warning()`.
3. THE ticker SHALL still be added to the queue (with the global date), but the user SHALL be informed that their date was not applied.

---

### Bug 14: list_history() Performance with Large Result Sets

**Severity:** MEDIUM
**File:** `dashboard/utils.py` — `list_history()` function
**Root Cause:** `list_history()` reads the ENTIRE JSON file (including all report text — market, news, fundamentals, sentiment, debate histories) for every saved analysis. With 500+ analyses, this loads hundreds of megabytes into memory on every 30-second cache refresh.

#### Acceptance Criteria

1. THE `list_history()` function SHALL continue to return full data (for backward compatibility with Chat context building).
2. A NEW `list_history_summary()` function SHALL be added that parses each JSON file but retains only lightweight fields in the returned dict: `company_of_interest` (as `ticker`), `trade_date` (as `date`), `final_trade_decision` (for rating extraction and executive summary), `portfolio_context`, and the `file` path. Full report text (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`, debate histories) SHALL NOT be retained in the returned records, allowing the full file content to be garbage collected.
3. THE History view's summary table SHALL use `list_history_summary()` for the initial list render.
4. THE History view SHALL load full data (via `load_run(json_file)`) only when the user expands a specific run's detail panel.
5. THE `list_history_summary()` function SHALL be cached with the same 30-second TTL as `list_history()`.

**Clarification:** The optimization is about memory retention, not disk I/O. Each JSON file must still be opened and parsed, but only the needed fields are kept in the cached result. For a 2MB analysis file, this reduces the cached footprint to ~5-10KB per record.

---

### Bug 15: sanitize_report() Overly Aggressive Tag Removal

**Severity:** MEDIUM
**File:** `dashboard/utils.py` — `sanitize_report()` function
**Root Cause:** The regex `r'<[^>]+>.*?</[^>]+>'` with `re.DOTALL` removes ANY paired HTML/XML tags and their content. This strips legitimate content like `<b>important</b>` or any HTML the LLM includes in reports. Also contains a duplicate `<tool_calls>` regex.

#### Acceptance Criteria

1. THE `sanitize_report()` function SHALL use an allowlist approach: strip all HTML/XML tags EXCEPT those in the HTML_ALLOWLIST (`<b>, <i>, <em>, <strong>, <table>, <tr>, <td>, <th>, <ul>, <ol>, <li>, <p>, <br>, <h1>-<h6>, <blockquote>, <code>, <pre>, <span>, <div>, <a>, <hr>`).
2. THE function SHALL always remove known problematic patterns regardless of allowlist: `<tool_calls>...</tool_calls>`, `<*>...</*>`, standalone `<parameter>` / `<tool_call>` tags, and `<script>...</script>` tags.
3. THE duplicate `<tool_calls>` regex SHALL be removed (currently applied twice).
4. THE function SHALL still return the "⚠️ Report generation failed" fallback message when the cleaned text is empty.
5. THE allowlist SHALL be defined as a module-level constant `_HTML_ALLOWLIST_TAGS` in `dashboard/utils.py` for easy maintenance.

---

### Bug 16: Executive Summary Not HTML-Escaped in Single Ticker View

**Severity:** MEDIUM
**File:** `dashboard/views/single_ticker.py` — `_render_reports()` line ~195
**Root Cause:** `exec_summary` is extracted from LLM output via regex and inserted directly into an HTML `<div>` with `unsafe_allow_html=True`. If the LLM output contains HTML/JS characters, they are rendered as HTML. The `sanitize_report()` function is NOT applied to `exec_summary` before insertion.

#### Acceptance Criteria

1. THE `exec_summary` text SHALL be HTML-escaped before insertion into the `<div>` element (using `html.escape()` or equivalent).
2. THE same escaping SHALL be applied to `price_target` and `time_horizon` values extracted from LLM output.
3. THE escaping SHALL preserve readability (e.g., `&amp;` for `&`, `&lt;` for `<`) without breaking the layout.

---

### Bug 17: time.sleep() Blocks Streamlit Server Thread

**Severity:** MEDIUM
**Files:** `dashboard/views/single_ticker.py` (last lines), `dashboard/views/watchlist.py` (last lines)
**Root Cause:** Both views use `time.sleep(2)` / `time.sleep(3)` followed by `st.rerun()` for auto-refresh during active runs. This blocks the entire Streamlit server thread for 2-3 seconds on every rerun, degrading performance for all users in multi-user deployments.

#### Acceptance Criteria

1. THE auto-refresh pattern SHALL be replaced with a non-blocking alternative.
2. THE preferred approach is `st.fragment` with `run_every=timedelta(seconds=2)` (available in Streamlit 1.33+) which refreshes only the fragment without blocking the server thread.
3. IF the installed Streamlit version is < 1.33 (check via `import streamlit; streamlit.__version__`), THE implementation SHALL fall back to the `streamlit-autorefresh` third-party component. IF neither is available, THE implementation SHALL retain the `time.sleep` pattern with a code comment documenting the limitation.
4. THE refresh interval SHALL remain at 2 seconds for single_ticker and 3 seconds for watchlist.
5. THE implementation SHALL check the Streamlit version at import time and select the appropriate refresh strategy, storing the choice in a module-level constant for consistency.
