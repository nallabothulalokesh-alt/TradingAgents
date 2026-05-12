# Requirements Document

## Introduction

This document covers seven targeted improvements to the existing "Watchlist" view in the TradingAgents Streamlit dashboard. The view is being renamed to "Multi-Ticker Analysis" to better reflect its purpose. The improvements enhance the result layout, add portfolio integration, replace the sequential queue with a configurable parallel worker pool, allow skipping running tickers, provide an at-a-glance sentiment summary chart, and add a shortcut to open all completed results in multi-analysis chat mode.

All changes are confined to `dashboard/views/watchlist.py` (logic and display) and `streamlit_app.py` (navigation label only). The file `watchlist.py` retains its name to avoid breaking imports.

**Dependencies:**
- Bug fixes 2, 3, 4 (thread safety) MUST be completed before Requirement 7 (parallel worker pool).
- Bug fix 17 (time.sleep replacement) should be done before or alongside this spec.
- The `compute_conviction()` shared utility (history-ux-improvements Req 9) should be available for the decision-first layout.

## Glossary

- **Dashboard**: The TradingAgents Streamlit web application.
- **Multi-Ticker Analysis View**: The renamed view previously called "Watchlist", implemented in `dashboard/views/watchlist.py` and rendered by `render_watchlist()`.
- **Queue**: The ordered list of tickers stored in `st.session_state["wl_queue"]` that are waiting to be analyzed.
- **Active_Workers**: The dict stored in `st.session_state["wl_active"]` mapping ticker string to its RunState object for all currently running analyses.
- **Worker_Pool**: The configurable set of concurrent analysis threads, bounded by the Max_Concurrency setting.
- **Max_Concurrency**: The maximum number of tickers that may be analyzed simultaneously, configurable by the user (range 1–5, default 3).
- **Result**: A dict stored in `st.session_state["wl_results"]` representing a completed (or errored or skipped) ticker analysis, containing keys `ticker`, `date`, `decision`, `error`, and `final_state`.
- **RunState**: The thread-safe object imported from `dashboard.runner` that tracks the progress of a single running analysis. Its `request_cancel()` method signals the background thread to stop.
- **Final_State**: The `final_state` dict inside a Result, containing analyst report fields (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`, `investment_plan`, `trader_investment_plan`, `final_trade_decision`).
- **Rating**: One of the five standard values: Buy, Overweight, Hold, Underweight, Sell. Extracted from the `decision` field of a Result.
- **Portfolio_File**: The JSON file at `~/.tradingagents/portfolio/portfolio.json` with schema `{"positions": [{"ticker": "NVDA", "shares": 10, ...}, ...]}`.
- **Executive_Summary**: The text extracted from the `**Executive Summary**` field of `final_trade_decision`, displayed inline without requiring a user click.
- **Rating_Distribution_Chart**: A horizontal bar chart or colored metric row showing the count of each Rating across all Results.
- **Chat_Multi_Mode**: The multi-analysis chat mode activated by setting `st.session_state["chat_mode"] = "multi"` and `st.session_state["chat_multi_prefill"]` to a list of `"{ticker}|{date}"` keys.

---

## Requirements

### Requirement 1: Rename to "Multi-Ticker Analysis"

**User Story:** As a user, I want the navigation and page header to say "Multi-Ticker Analysis", so that the view's purpose is immediately clear.

#### Acceptance Criteria

1. THE Dashboard SHALL display the navigation option for this view as `"📊 Multi-Ticker Analysis"` in the sidebar radio widget defined in `streamlit_app.py`.
2. THE Multi-Ticker_Analysis_View SHALL render the page title as `"📊 Multi-Ticker Analysis"` via `st.title()`.
3. THE Multi-Ticker_Analysis_View SHALL render the page caption as `"Analyse multiple tickers in parallel — results accumulate as each completes."` via `st.caption()`.
4. THE Dashboard SHALL route the `"📊 Multi-Ticker Analysis"` navigation option to `render_watchlist()` in `streamlit_app.py`.
5. THE Dashboard SHALL NOT rename the file `watchlist.py` or change the function name `render_watchlist()`.

---

### Requirement 2: Decision-First Layout in Expanded Results

**User Story:** As a user, I want to see the trading decision and key metrics immediately when I expand a completed result, so that I can assess the outcome without scrolling through tabs.

#### Acceptance Criteria

1. WHEN a user expands a completed Result that has no error, THE Multi-Ticker_Analysis_View SHALL render a decision banner as the first element, displaying the Rating with its associated color from `RATING_COLORS`.
2. WHEN a user expands a completed Result that has no error, THE Multi-Ticker_Analysis_View SHALL render a key metrics row below the decision banner, displaying Price Target and Time Horizon values extracted from `final_trade_decision` text using regex patterns `\*\*Price Target\*\*[:\s]+([^\n]+)` and `\*\*Time Horizon\*\*[:\s]+([^\n]+)`.
3. WHEN a user expands a completed Result that has no error, THE Multi-Ticker_Analysis_View SHALL render the Executive_Summary (content of `final_trade_decision`) inline and visible without any additional user interaction.
4. WHEN a user expands a completed Result that has no error, THE Multi-Ticker_Analysis_View SHALL render each available analyst report (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`) as an individual `st.expander` widget that is collapsed by default.
5. WHEN a user expands a completed Result that has no error, THE Multi-Ticker_Analysis_View SHALL render Research Plan (`investment_plan`), Trader Plan (`trader_investment_plan`), and Final Decision (`final_trade_decision`) as individual `st.expander` widgets below the analyst report expanders, collapsed by default.
6. IF a `final_trade_decision` field does not contain a Price Target or Time Horizon pattern, THEN THE Multi-Ticker_Analysis_View SHALL omit the corresponding metric from the key metrics row and MAY display an informational message indicating the metric was not found.
7. WHEN a user expands a completed Result that has an error, THE Multi-Ticker_Analysis_View SHALL display the error message using `st.error()` as the only content in the expander.
8. WHEN a user expands a Result that is neither completed nor errored (i.e., `final_state` is null and `error` is null), THE Multi-Ticker_Analysis_View SHALL render a loading or pending state indicator as the expander content.

**Correctness Properties:**

- For any `final_trade_decision` string, the count of metric fields rendered in the key metrics row SHALL equal the count of regex patterns that match within that string (0, 1, or 2).
- For any Result with a non-null `final_state`, the number of analyst report expanders rendered SHALL equal the number of non-null report fields among `market_report`, `news_report`, `fundamentals_report`, and `sentiment_report`.

---

### Requirement 3: Import from Portfolio

**User Story:** As a user, I want to import tickers from my portfolio into the ticker text area, so that I can quickly queue all my holdings for analysis without manual entry.

#### Acceptance Criteria

1. THE Multi-Ticker_Analysis_View SHALL render an `"📂 Import from Portfolio"` button in the sidebar, below the ticker text area.
2. WHEN the user clicks `"📂 Import from Portfolio"` and the Portfolio_File exists and contains at least one position with a non-empty ticker, THE Multi-Ticker_Analysis_View SHALL append only the tickers from the portfolio that are NOT already present in the ticker text area (case-insensitive deduplication), separated by newlines. Tickers already in the text area SHALL NOT be duplicated.
3. WHEN the user clicks `"📂 Import from Portfolio"` and the Portfolio_File does not exist, THE Multi-Ticker_Analysis_View SHALL display an informational message using `st.info()` stating that no portfolio file was found and indicating the expected path.
4. WHEN the user clicks `"📂 Import from Portfolio"` and the Portfolio_File exists but contains no positions or an empty positions list, THE Multi-Ticker_Analysis_View SHALL display an informational message using `st.info()` stating that the portfolio is empty.
5. WHEN the user clicks `"📂 Import from Portfolio"` and the Portfolio_File exists but cannot be parsed as valid JSON, THE Multi-Ticker_Analysis_View SHALL display an error message using `st.error()`.
6. THE Multi-Ticker_Analysis_View SHALL read the Portfolio_File from the path `~/.tradingagents/portfolio/portfolio.json`, expanding the `~` to the user's home directory.
7. THE Multi-Ticker_Analysis_View SHALL extract ticker values from the `positions` array in the Portfolio_File, using the `ticker` key of each position object.

---

### Requirement 3b: Per-Ticker Date Validation

**User Story:** As a user using per-ticker date override, I want to see a clear warning when a date I entered is in the wrong format, so that I know my date was not applied.

#### Acceptance Criteria

1. WHEN per-ticker date override is enabled and a line contains a date string that cannot be parsed as `YYYY-MM-DD`, THE Multi-Ticker_Analysis_View SHALL display a per-line warning: `"{TICKER}: date '{entered_date}' is not valid (use YYYY-MM-DD format) — using global date instead."` rather than silently falling back to the global date.
2. THE warning SHALL be displayed inline in the sidebar after the "Add to Queue" action, not as a blocking error.

---

### Requirement 3c: Add Tickers Mid-Batch

**User Story:** As a user running a batch analysis, I want to add more tickers to the queue while the batch is running, so that I don't have to wait for the whole batch to finish if I forgot a ticker.

#### Acceptance Criteria

1. WHEN a batch is running, THE Multi-Ticker_Analysis_View SHALL keep the ticker text area and "Add to Queue" button enabled (not disabled).
2. WHEN the user adds tickers while a batch is running, THE Multi-Ticker_Analysis_View SHALL validate each ticker before appending it to the Queue (consistent with the initial add behavior) and SHALL reject invalid tickers with an inline error message. Valid tickers SHALL be appended to the end of the Queue and the Worker_Pool SHALL pick them up as slots become free.
3. THE Multi-Ticker_Analysis_View SHALL display the updated queue length immediately after new tickers are added mid-batch.

**Bug Fix Note (existing code):** The current "Add to Queue" button has `disabled=st.session_state["wl_running"]` which prevents adding tickers mid-batch. This must be removed. Additionally, the current ticker parsing logic (`parts = line.split(); ticker = parts[0].upper()`) only takes the first word from each line — if a user enters "NVDA AAPL TSLA" on one line (space-separated), only "NVDA" is parsed and "AAPL TSLA" are silently dropped. The parser should handle comma-separated values on a single line (which it does via `.replace(",", "\n")`) but NOT space-separated values (since spaces are used for per-ticker date override like "NVDA 2026-05-01"). This behavior should be documented in the text area placeholder.

---

### Requirement 3d: Batch Presets

**Phase:** DEFERRED to Phase 2 — implement after core parallel pool and batch features are stable.

**User Story:** As a user who runs the same set of tickers regularly, I want to save and recall named ticker lists, so that I don't have to re-type them every time.

#### Acceptance Criteria

1. THE Multi-Ticker_Analysis_View SHALL provide a "💾 Save as preset" button that saves the current ticker text area content to a named preset stored at `~/.tradingagents/presets/<name>.txt`.
2. WHEN the user clicks "Save as preset", THE Multi-Ticker_Analysis_View SHALL prompt for a preset name using a text input and SHALL NOT save if the name is empty.
3. THE Multi-Ticker_Analysis_View SHALL provide a "📂 Load preset" dropdown that lists all saved presets. WHEN the user selects a preset, THE Multi-Ticker_Analysis_View SHALL replace the ticker text area content with the preset's tickers.
4. THE Multi-Ticker_Analysis_View SHALL provide a "🗑 Delete preset" button next to the Load preset dropdown that deletes the currently selected preset after confirmation.

---

### Requirement 4: Skip Active Ticker

**User Story:** As a user, I want to skip any currently running ticker, so that I can move on without waiting for a slow or stuck analysis to finish.

#### Acceptance Criteria

1. WHILE one or more tickers are actively running, THE Multi-Ticker_Analysis_View SHALL render a `"⏭ Skip"` button adjacent to each active ticker's progress display in the Active_Workers section.
2. WHEN the user clicks `"⏭ Skip"` for a specific ticker, THE Multi-Ticker_Analysis_View SHALL call `request_cancel()` on that ticker's RunState object in `st.session_state["wl_active"]`.
3. WHEN the user explicitly clicks `"⏭ Skip"` for a ticker, THE Multi-Ticker_Analysis_View SHALL append a Result to `st.session_state["wl_results"]` with `decision` set to `"Skipped"`, `error` set to `None`, and `final_state` set to `None` for that ticker. System-initiated cancellations SHALL NOT append a Skipped result.
4. WHEN the user clicks `"⏭ Skip"` for a ticker, THE Multi-Ticker_Analysis_View SHALL remove that ticker from `st.session_state["wl_active"]` and SHALL dispatch the next queued ticker to fill the freed worker slot if the Queue is non-empty.
5. WHILE no tickers are actively running, THE Multi-Ticker_Analysis_View SHALL NOT render any `"⏭ Skip"` buttons.
6. WHEN the user clicks `"⏭ Skip"` and both the Queue and Active_Workers are empty after skipping, THE Multi-Ticker_Analysis_View SHALL set `st.session_state["wl_running"]` to `False`.

---

### Requirement 5: Results Summary Chart

**User Story:** As a user, I want to see a rating distribution visualization above the results table, so that I can get an at-a-glance view of the overall sentiment across all analyzed tickers.

#### Acceptance Criteria

1. WHEN at least one Result is present in `st.session_state["wl_results"]`, THE Multi-Ticker_Analysis_View SHALL render a Rating_Distribution_Chart above the results summary table.
2. THE Rating_Distribution_Chart SHALL display the count of Results for each of the five standard Ratings (Buy, Overweight, Hold, Underweight, Sell) and a count for Error results.
3. THE Rating_Distribution_Chart SHALL use the color from `RATING_COLORS` for each Rating's visual representation.
4. THE Rating_Distribution_Chart SHALL only include Rating categories that have a count greater than zero.
5. WHEN no Results are present, THE Multi-Ticker_Analysis_View SHALL NOT render the Rating_Distribution_Chart.

**Correctness Properties:**

- For any list of Results, the sum of all per-Rating counts displayed in the Rating_Distribution_Chart SHALL equal the total number of Results in the list.
- For any list of Results, the count displayed for each Rating SHALL equal the number of Results whose `decision` field matches that Rating exactly.

---

### Requirement 6: "Analyze in Chat" Shortcut

**User Story:** As a user, I want to open completed results in multi-analysis chat mode — either all of them or a selected subset — so that I can ask targeted questions across the analyses I care about.

#### Acceptance Criteria

1. WHEN at least 2 completed (non-error) Results are present in `st.session_state["wl_results"]`, THE Multi-Ticker_Analysis_View SHALL render a checkbox next to each completed Result row in the results table.
2. WHEN no checkboxes are checked, THE Multi-Ticker_Analysis_View SHALL render an `"Analyze all in Chat"` button that includes all completed (non-error, non-skipped) Results.
3. WHEN one or more checkboxes are checked, THE Multi-Ticker_Analysis_View SHALL render an `"Analyze selected in Chat"` button that includes only the checked Results.
4. WHEN fewer than 2 completed (non-error) Results are present, THE Multi-Ticker_Analysis_View SHALL NOT render any chat button or checkboxes.
5. WHEN the user clicks either chat button, THE Multi-Ticker_Analysis_View SHALL set `st.session_state["chat_multi_prefill"]` to a list of `"{ticker}|{date}"` strings for the applicable Results, set `st.session_state["chat_mode"]` to `"multi"`, set `st.session_state["_nav_target"]` to `"💬 Analysis Chat"`, and call `st.rerun()`.
6. THE Multi-Ticker_Analysis_View SHALL exclude Results with a non-null `error` field from the prefill list regardless of checkbox state.
7. THE Multi-Ticker_Analysis_View SHALL exclude Results with `decision` equal to `"Skipped"` from the prefill list regardless of checkbox state.
8. WHEN the "Analyze selected in Chat" button is clicked and fewer than 2 checked Results are eligible (after excluding errors and skipped), THE Multi-Ticker_Analysis_View SHALL display a validation message and SHALL NOT navigate.
9. WHEN exactly 2 Results are checked in the results table, THE Multi-Ticker_Analysis_View SHALL also render a "⚖️ Compare these two" button. WHEN clicked, THE Multi-Ticker_Analysis_View SHALL set `st.session_state["cmp_filter_a"]` to the ticker of the first checked result, `st.session_state["cmp_filter_b"]` to the ticker of the second checked result, and `st.session_state["_nav_target"]` to `"⚖️ Compare"`, then call `st.rerun()`.
10. WHEN any "Open in Chat" or "Analyze in Chat" button is clicked, THE Multi-Ticker_Analysis_View SHALL call `invalidate_history_cache()` BEFORE setting `_nav_target`, so that the target view's `list_history()` call picks up the newly saved analysis files even if the batch is still running.

**Correctness Properties:**

- WHEN "Analyze all in Chat" is clicked, the length of `chat_multi_prefill` SHALL equal the count of Results where `error` is null and `decision` is not `"Skipped"`.
- WHEN "Analyze selected in Chat" is clicked, the length of `chat_multi_prefill` SHALL equal the count of checked Results where `error` is null and `decision` is not `"Skipped"`.

---

### Requirement 7: Parallel Worker Pool

**User Story:** As a user with multiple tickers to analyse, I want analyses to run concurrently up to a configurable limit, so that a 10-ticker batch completes in roughly 1/N of the time instead of sequentially.

#### Acceptance Criteria

1. THE Multi-Ticker_Analysis_View SHALL replace the existing single-thread sequential runner (`_start_next` chain) with a Worker_Pool that dispatches up to Max_Concurrency analyses simultaneously, each in its own background thread.
2. THE Multi-Ticker_Analysis_View SHALL expose a "Max concurrent analyses" slider in the sidebar with a range of 1 to 5 and a default value of 3.
3. WHEN the user sets Max_Concurrency to 1, THE Multi-Ticker_Analysis_View SHALL behave identically to the previous sequential model — only one ticker runs at a time.
4. WHEN the batch is started, THE Multi-Ticker_Analysis_View SHALL immediately dispatch up to Max_Concurrency tickers from the Queue, each as a separate background thread with its own RunState.
5. WHEN any active ticker completes (success, error, or skip), THE Multi-Ticker_Analysis_View SHALL automatically dispatch the next queued ticker to fill the freed worker slot, maintaining up to Max_Concurrency active workers at all times until the Queue is empty.
6. THE Multi-Ticker_Analysis_View SHALL store all currently active RunState objects in `st.session_state["wl_active"]` as a dict keyed by ticker string, replacing the previous single `st.session_state["wl_current"]` object.
7. THE Multi-Ticker_Analysis_View SHALL display a separate progress tracker (agent status indicators and last log line) for each entry in `st.session_state["wl_active"]` simultaneously in the "Currently Running" section.
8. WHEN `st.session_state["wl_active"]` is empty and `st.session_state["wl_queue"]` is empty, THE Multi-Ticker_Analysis_View SHALL set `st.session_state["wl_running"]` to `False` and invalidate the history cache.
9. THE Worker_Pool SHALL use a module-level `threading.Lock` (`_results_lock`) to protect all reads and writes to `_results_buffer`. THE `st.session_state["wl_active"]` dict SHALL only be read and written by the main Streamlit thread — background threads SHALL NOT access it directly or indirectly.
10. WHEN Max_Concurrency is changed by the user while a batch is running, THE Multi-Ticker_Analysis_View SHALL apply the new value only to future slot-fill dispatches — already-running analyses SHALL NOT be interrupted. THE main thread SHALL NOT dispatch new workers while `len(wl_active) >= Max_Concurrency` (using the current slider value), even if the value was recently reduced from a higher number.

**Correctness Properties:**

- At any point during a running batch, the count of entries in `st.session_state["wl_active"]` SHALL be greater than zero and less than or equal to Max_Concurrency, unless the Queue is empty and all remaining active workers are finishing.
- The total count of Results appended to `st.session_state["wl_results"]` at batch completion SHALL equal the total number of tickers that were in the Queue when the batch was started, including any that were skipped or errored.

---

### Requirement 11: Fast Mode for Batch Analysis

**User Story:** As a user running a batch analysis on tickers I've analysed recently, I want Fast Mode to automatically reuse fundamentals and research plans from prior runs, so that I save time and API cost without sacrificing freshness on market data and news.

#### Acceptance Criteria

1. THE Multi-Ticker_Analysis_View SHALL expose a "⚡ Fast Mode" toggle in the sidebar with a default value of off.
2. WHEN Fast Mode is enabled, THE Multi-Ticker_Analysis_View SHALL expose a "Max days to look back" slider (range 1–14, default 7) that controls how old a prior run can be for its data to be reused.
3. WHEN Fast Mode is enabled and a ticker is dispatched for analysis, THE Multi-Ticker_Analysis_View SHALL call `find_recent_run(ticker, trade_date, max_days)` to check for a prior run within the configured lookback window.
4. WHEN a prior run is found for a ticker, THE Multi-Ticker_Analysis_View SHALL pass that prior run to `run_analysis()` as the `prior_run` parameter, enabling Fast Mode for that ticker (reusing fundamentals + research plan, running market/news/trader/risk/PM fresh).
5. WHEN no prior run is found for a ticker, THE Multi-Ticker_Analysis_View SHALL run a full analysis for that ticker regardless of the Fast Mode toggle.
6. THE Multi-Ticker_Analysis_View SHALL display a "📦 Fast" badge next to each ticker in the active workers display when that ticker is running in Fast Mode, and a "🔄 Full" badge when running a full analysis.
7. WHEN Fast Mode is enabled and a prior run exists for a ticker, THE Multi-Ticker_Analysis_View SHALL check for stale fundamentals using `check_stale_fundamentals()` and display a per-ticker warning in the results table if earnings occurred between the prior run date and the analysis date.
8. THE Fast Mode toggle and lookback slider SHALL be disabled while a batch is running.
9. WHEN `check_stale_fundamentals()` returns a warning for a completed ticker, THE Multi-Ticker_Analysis_View SHALL display a "🔄 Re-run Full" button next to that ticker's result that allows the user to re-queue that single ticker for a Full Mode analysis (ignoring the Fast Mode toggle for that ticker only).

**Correctness Properties:**

- For any ticker in a batch, if Fast Mode is enabled and a prior run exists within the lookback window, the ticker SHALL run in Fast Mode. If no prior run exists, the ticker SHALL run in Full Mode regardless of the Fast Mode toggle.

**User Story:** As a user browsing History, I want to see which past analyses were run with portfolio ownership context, so that I can distinguish portfolio-aware recommendations from generic ones.

#### Acceptance Criteria

1. WHEN an analysis is initiated from the Multi-Ticker Analysis view with ownership context injected (i.e. the ticker exists in the Portfolio_File), THE Multi-Ticker_Analysis_View SHALL pass the ownership context string to `run_analysis()` as the `portfolio_context` parameter.
2. THE `run_analysis()` function SHALL write the `portfolio_context` string into the saved `full_states_log_<DATE>.json` file under the top-level key `"portfolio_context"` after `_log_state()` writes the file.
3. WHEN no ownership context is injected for a ticker, THE Multi-Ticker_Analysis_View SHALL pass `portfolio_context=None` to `run_analysis()` and no `"portfolio_context"` key SHALL be written to the JSON.
4. THE History view SHALL display a `"🏦 Portfolio run"` badge on any Run_Record whose saved JSON contains a non-empty `"portfolio_context"` field.
5. THE addition of the `"portfolio_context"` field SHALL NOT break any existing code that reads `full_states_log_<DATE>.json`.

---

### Requirement 9: Thread-Safe Parallel Worker Pool (Gap 4)

**User Story:** As a developer, I want the parallel worker pool to be thread-safe so that background threads never corrupt Streamlit session state.

#### Acceptance Criteria

1. THE Worker_Pool implementation SHALL follow the existing module-level buffer pattern: background threads SHALL only write to the module-level `_results_buffer` list (protected by `_results_lock`), and SHALL NOT write directly to `st.session_state`.
2. THE main Streamlit thread SHALL drain `_results_buffer` into `st.session_state["wl_results"]` at the start of each render cycle, before any UI is rendered.
3. THE `st.session_state["wl_active"]` dict SHALL only be written by the main Streamlit thread — when dispatching a new worker (adding an entry) and when draining completed results from `_results_buffer` (removing the entry for the completed ticker).
4. WHEN a background thread completes (success, error, or cancellation), it SHALL append its result to `_results_buffer` and SHALL NOT modify `st.session_state["wl_active"]` directly.
5. THE `_results_buffer` list and `_results_lock` SHALL be module-level variables in `watchlist.py`, consistent with the existing pattern.
6. THE main Streamlit thread SHALL handle all queue advancement (dispatching the next ticker when a slot frees up) — background threads SHALL NOT call any function that reads or writes `st.session_state`, including the existing `_start_next()` pattern which is unsafe and must be replaced.
7. WHEN multiple Streamlit sessions are active simultaneously, THE `_results_buffer` SHALL be keyed by a session-unique identifier (e.g., `st.session_state` session ID or a UUID generated at session start) so that results from one user's batch do not leak into another user's session. Alternatively, THE implementation MAY document that multi-user concurrent watchlist execution is not supported and accept the single-user limitation.

**Bug Fix Note (existing code):** The current implementation calls `_start_next()` from within `_on_done()` which runs on a background thread. This accesses `st.session_state` from a non-main thread, which is undefined behavior in Streamlit and can cause `RuntimeError` or silent state corruption. The new Worker_Pool MUST eliminate this pattern entirely.

---

### Requirement 10: Trader Plan Key Name Compatibility

**User Story:** As a developer, I want the Multi-Ticker Analysis view to correctly display the Trader Plan for all saved analyses regardless of which key name was used when the file was saved.

#### Acceptance Criteria

1. WHEN rendering the Trader Plan expander in an expanded Result, THE Multi-Ticker_Analysis_View SHALL read the trader plan content using the fallback expression `final_state.get("trader_investment_decision") or final_state.get("trader_investment_plan")` to handle both the legacy key name and the current key name.
2. THE Multi-Ticker_Analysis_View SHALL NOT assume either key name is exclusively present.

**Bug Fix Note (existing code):** The current watchlist view only reads `final_state.get("trader_investment_plan")`. Analyses saved before the key was renamed use `trader_investment_decision`. This causes the Trader Plan section to appear empty for older analyses.

---

### Requirement 12: Fast Mode Graph Must Skip Research Team (Bug Fix)

**User Story:** As a developer, I want Fast Mode to actually skip the research team agents so that the pre-seeded `investment_plan` is not overwritten by the Research Manager node.

#### Acceptance Criteria

1. WHEN Fast Mode is enabled for a ticker, THE `_build_fast_graph()` function in `dashboard/runner.py` SHALL build a custom LangGraph that does NOT include Bull Researcher, Bear Researcher, or Research Manager nodes.
2. THE Fast Mode graph SHALL connect the last analyst's "Msg Clear" node directly to the Trader node, bypassing the research debate entirely.
3. THE pre-seeded `investment_plan` in the initial state SHALL be preserved through the graph execution and SHALL NOT be overwritten by any node.
4. THE Fast Mode graph SHALL still include: selected analyst nodes (market, news, social), Trader, Risk Team (Aggressive/Conservative/Neutral Analysts), and Portfolio Manager.
5. THE `_build_fast_graph()` function SHALL NOT call `GraphSetup.setup_graph()` (which always builds the full pipeline including researchers). It SHALL construct the reduced graph directly using `StateGraph` and explicit node/edge additions.

**Bug Fix Note (existing code):** The current `_build_fast_graph()` calls `fast_setup.setup_graph(fast_analysts)` which ALWAYS adds Bull Researcher → Bear Researcher → Research Manager → Trader edges. This means the Research Manager node runs and overwrites the pre-seeded `investment_plan`, completely defeating the purpose of Fast Mode. The graph must be built manually to skip these nodes.

---

### Requirement 13: RunState Attribute Assignment Thread Safety (Bug Fix)

**User Story:** As a developer, I want all RunState attribute mutations to go through the lock so that the main thread never reads partially-written state.

#### Acceptance Criteria

1. THE `run_analysis()` function in `dashboard/runner.py` SHALL set `running`, `ticker`, `trade_date`, and `agent_status` on the RunState object using a single locked block (or individual locked setters), not via direct attribute assignment outside the lock.
2. THE `_worker()` function SHALL NOT redundantly re-assign `running`, `ticker`, `trade_date`, and `agent_status` — these SHALL be set exactly once, before the thread is spawned, under the lock.
3. THE `RunState` class SHALL expose a `start(ticker, trade_date, agent_status)` method that sets all four fields atomically under `self._lock`, replacing the current pattern of multiple unlocked assignments.

**Bug Fix Note (existing code):** `run_analysis()` sets `run_state.running = True`, `run_state.ticker = ticker`, etc. directly (bypassing the lock) on lines ~185-192, and then `_worker()` does the same thing again on lines ~198-204. This creates a race window where `snapshot()` could read inconsistent state.
