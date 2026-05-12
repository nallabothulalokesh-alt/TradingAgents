# Requirements Document

## Introduction

The Portfolio Management feature adds a dedicated **Portfolio** view to the TradingAgents Streamlit dashboard. Users can manually enter and persist stock positions (ticker + shares), view a live overview of their portfolio's current market value, and run AI-powered analysis on their holdings — either as a batch sweep across all positions or as a deep-dive on any individual position. The Portfolio Manager agent is made ownership-aware: when analysing a held ticker it receives the user's current share count so it can tailor recommendations (e.g., "consider trimming" vs. "consider adding to position"). Portfolio data is stored locally in a JSON file so it survives application restarts.

**Dependencies:**
- Memory JSON migration (for `load_memory_entries()` reliability in Portfolio Overview joins)
- Bug fixes 2, 3, 4 (thread safety for batch analysis)
- Multi-Ticker Analysis parallel Worker_Pool (Req 7) — Portfolio batch reuses this infrastructure
- `compute_conviction()` shared utility (history-ux-improvements Req 9)
- `run_analysis()` portfolio_context parameter (this spec's Req 14)
- Shared decision-first rendering utility (cross-cutting-concerns.md)

**Implementation Note:** This is the largest spec and depends on most other specs being complete. It should be implemented last.

---

## Glossary

- **Portfolio**: The user's collection of stock positions, each consisting of a ticker symbol and a share count.
- **Position**: A single entry in the Portfolio, identified by a unique ticker symbol and a non-negative share count.
- **Portfolio_Store**: The component responsible for reading and writing portfolio data to `~/.tradingagents/portfolio/portfolio.json`.
- **Portfolio_View**: The Streamlit UI page rendered at the "💼 Portfolio" navigation entry.
- **Portfolio_Overview**: The live summary table in Portfolio_View showing current price, position value, total portfolio value, and last analysis rating for all positions.
- **Last_Analysis_Badge**: A colored rating pill and date shown per position in the Portfolio_Overview, derived by joining portfolio positions with `list_history()` results by ticker.
- **Batch_Analysis**: A mode that runs the full TradingAgents pipeline concurrently (up to Max_Concurrency workers) for every position in the Portfolio, reusing the Worker_Pool from the Multi-Ticker Analysis view.
- **Individual_Analysis**: A mode that runs the full TradingAgents pipeline for a single selected position.
- **Ownership_Context**: A string injected into the Portfolio Manager agent's prompt that states the user's current share count for the ticker being analysed.
- **Portfolio_Run_Flag**: An optional field `portfolio_context` saved into the analysis JSON log (`full_states_log_<DATE>.json`) when an analysis is initiated from the Portfolio_View, containing the Ownership_Context string that was injected.
- **TradingAgentsGraph**: The existing LangGraph-based multi-agent pipeline, entry point `TradingAgentsGraph.propagate(ticker, date)`.
- **past_context**: The existing string field in the LangGraph initial state that carries memory and contextual information into the Portfolio Manager agent's prompt.
- **Max_Concurrency**: The maximum number of tickers that may be analysed simultaneously in Batch_Analysis, inherited from the Multi-Ticker Analysis Worker_Pool setting (range 1–5, default 3).
- **Dashboard**: The Streamlit application defined in `streamlit_app.py` and `dashboard/views/`.
- **yfinance**: The Python library used to fetch live market price data.

---

## Requirements

### Requirement 1: Portfolio Navigation Entry

**User Story:** As a trader, I want a dedicated Portfolio page in the dashboard navigation, so that I can access my portfolio management tools without leaving the application.

#### Acceptance Criteria

1. THE Dashboard SHALL display a "💼 Portfolio" entry in the sidebar navigation radio group alongside the existing views (Single Ticker, Watchlist, History, Compare, Analysis Chat).
2. WHEN the user selects "💼 Portfolio" from the navigation, THE Dashboard SHALL render the Portfolio_View without reloading the page.
3. THE Dashboard SHALL preserve the existing navigation order, inserting "💼 Portfolio" after "📊 Multi-Ticker Analysis" (the renamed Watchlist view).

---

### Requirement 2: Portfolio Data Persistence

**User Story:** As a trader, I want my portfolio positions saved locally, so that my holdings are still present after I restart the application.

#### Acceptance Criteria

1. THE Portfolio_Store SHALL persist portfolio data to `~/.tradingagents/portfolio/portfolio.json` using UTF-8 encoding.
2. WHEN the portfolio file does not exist, THE Portfolio_Store SHALL initialise it with an empty positions list on first write.
3. THE Portfolio_Store SHALL use a JSON schema where each position object contains at minimum the fields `ticker` (string), `shares` (number), and `added_at` (ISO-8601 datetime string), and MAY contain additional optional fields (e.g., `cost_basis`) to support future extensions without requiring a schema migration.
4. WHEN a write operation fails due to a filesystem error, THE Portfolio_Store SHALL surface a descriptive error message to the caller and leave the existing file unchanged.
5. WHEN the portfolio file exists but contains malformed JSON, THE Portfolio_Store SHALL display a prominent error banner: "⚠️ Portfolio file is corrupted. Your data is preserved at [path]. Please fix or delete the file to start fresh." THE Portfolio_View SHALL NOT silently treat the portfolio as empty — it SHALL show this banner and render no positions until the file is fixed or deleted.
6. WHEN a write operation is attempted and the `~/.tradingagents/portfolio/` directory does not exist, THE Portfolio_Store SHALL create the directory before writing.
7. ALL write operations to the portfolio file SHALL use the atomic write pattern: write to a temporary file in the same directory, then rename (move) the temporary file to the target path. This ensures that a crash or power loss mid-write never leaves a corrupted or partial portfolio file.
8. IF the atomic rename fails (e.g., target file locked by another process — common on NTFS/WSL), THE Portfolio_Store SHALL retry once after a 100ms delay. IF the retry also fails, THE Portfolio_Store SHALL fall back to a direct write (non-atomic) and log a warning: "Atomic write failed, falling back to direct write. Data integrity is not guaranteed if the application crashes during this operation."

---

### Requirement 3: Add and Remove Positions

**User Story:** As a trader, I want to manually add and remove stock positions in my portfolio, so that I can keep my holdings up to date.

#### Acceptance Criteria

1. THE Portfolio_View SHALL provide an input form accepting a ticker symbol and a share count for adding a new position.
2. WHEN the user submits a new position, THE Portfolio_View SHALL validate the ticker symbol against yfinance before saving, and SHALL display a descriptive error if the ticker is invalid. WHILE the user is typing a ticker symbol, THE Portfolio_View SHALL perform real-time validation and display inline feedback before the form is submitted.
3. WHEN the user submits a new position with a share count less than or equal to zero, THE Portfolio_View SHALL display a descriptive error and SHALL NOT save the position.
4. WHEN the user submits a valid position for a ticker that already exists in the Portfolio, THE Portfolio_View SHALL REPLACE the share count of the existing position with the new value (not add to it), and SHALL display a confirmation message: "NVDA position updated to {shares} shares." IF the update operation fails, THEN THE Portfolio_View SHALL display a descriptive error and SHALL NOT create a duplicate entry. THE Portfolio_View SHALL display a prominent preview label (styled as a warning) below the share count input when the ticker already exists: "⚠️ You currently hold {existing_shares} shares. Submitting will replace this with {new_shares} shares." This preview SHALL be visible before the user clicks submit, so they can confirm the change is intentional.
5. WHEN the user removes a position, THE Portfolio_View SHALL delete that position from the Portfolio and persist the change immediately.
6. WHEN a position is successfully added or updated, THE Portfolio_Store SHALL record the current UTC datetime in the `added_at` field.

---

### Requirement 4: Live Portfolio Overview

**User Story:** As a trader, I want to see the current market value of each position and my total portfolio value alongside the last analysis rating, so that I can monitor my exposure and analysis freshness at a glance.

#### Acceptance Criteria

1. THE Portfolio_Overview SHALL display a table with one row per position containing: ticker symbol, share count, current price (USD), position value (shares × current price), last analysis rating (with date), and a remove action.
2. WHEN the Portfolio_View is rendered, THE Portfolio_Overview SHALL fetch the current price for ALL positions using `yf.download()` with all tickers in a single batch call (yfinance supports multi-ticker download natively and it's significantly faster than individual calls). IF `yf.download()` fails or returns partial results, THE Portfolio_Overview SHALL fall back to parallel individual fetches using `concurrent.futures.ThreadPoolExecutor` with `max_workers=10` to avoid triggering yfinance rate limits. THE Portfolio_Overview SHALL display a loading spinner while prices are being fetched.
3. THE Portfolio_Overview SHALL display the total portfolio value as the sum of all individual position values for which a valid price was returned. WHEN individual position price fetches return inconsistent or failed results, THE Portfolio_Overview SHALL recalculate the total independently from the raw fetched price data, and the displayed total MAY differ from the sum of the displayed per-position values if any position's displayed value is stale or unavailable.
4. IF yfinance returns no price data for a ticker, THEN THE Portfolio_Overview SHALL display "N/A" for that position's price and value and SHALL NOT include it in the total portfolio value calculation. The fetch failure for one ticker SHALL NOT block or delay the display of other tickers' prices.
5. THE Portfolio_Overview SHALL display a "Prices as of X minutes ago" timestamp reflecting when the price data was last fetched.
6. THE Portfolio_View SHALL provide a manual refresh button that re-fetches all current prices from yfinance and updates the Portfolio_Overview.
7. THE Portfolio_Overview SHALL derive the Last_Analysis_Badge for each position by joining the portfolio positions with `list_history()` results by ticker, selecting the most recent run by date. WHEN a position has at least one saved analysis, THE Portfolio_Overview SHALL display the rating as a colored pill and the analysis date. WHEN a position has no saved analyses, THE Portfolio_Overview SHALL display "Not analysed" in the last analysis column with no warning icon.
8. THE Portfolio_Overview SHALL display a ⚠️ stale indicator only for positions whose most recent analysis date exists AND is older than 7 days, so the user can identify analyses that need refreshing. Positions with no analysis SHALL NOT display the ⚠️ indicator.
9. WHEN any analysis completes (batch or individual) from the Portfolio_View, THE Portfolio_Overview SHALL invalidate the `list_history()` cache and re-fetch the last analysis data so that the updated rating and date are reflected immediately without waiting for the 30-second cache TTL.
10. THE Portfolio_View SHALL provide an auto-refresh toggle for prices with options: Off (default), 1 minute, 5 minutes, 15 minutes. WHEN auto-refresh is enabled, THE Portfolio_Overview SHALL automatically re-fetch all prices at the selected interval and update the "Prices as of X minutes ago" timestamp.

---

### Requirement 5: Ownership Context Injection

**User Story:** As a trader, I want the Portfolio Manager agent to know how many shares I hold when analysing a position, so that its recommendations are relevant to my actual situation.

#### Acceptance Criteria

1. WHEN an analysis is initiated from the Portfolio_View for a ticker that exists in the Portfolio, THE Dashboard SHALL construct an Ownership_Context string of the form: `"Portfolio context: You currently hold {shares} shares of {ticker}."`.
2. WHEN an analysis is initiated from the Portfolio_View, THE Dashboard SHALL prepend the Ownership_Context to the `past_context` field of the LangGraph initial state before passing it to TradingAgentsGraph.
3. WHEN an analysis is initiated from the Portfolio_View for a ticker that does NOT exist in the Portfolio, THE Dashboard SHALL NOT inject any Ownership_Context and SHALL pass `past_context` unchanged.
4. THE Portfolio Manager agent's prompt SHALL include the Ownership_Context when it is present in `past_context`, without requiring any changes to the agent's internal prompt template beyond what is already supported by the existing `past_context` injection mechanism.
5. WHEN the Ownership_Context is injected, THE Portfolio Manager agent SHALL receive the share count that was current in the Portfolio at the time the analysis was initiated (i.e., when `run_analysis()` is called). The share count is baked into the `past_context` field of the LangGraph initial state and cannot be updated mid-run. IF the user updates their position while an analysis is running, the running analysis will use the share count from initiation time — this is expected and acceptable behavior.

---

### Requirement 6: Batch Portfolio Analysis

**User Story:** As a trader, I want to analyse all my portfolio positions in parallel, so that I can get a holistic view of my holdings quickly without waiting for each ticker to finish sequentially.

#### Acceptance Criteria

1. THE Portfolio_View SHALL provide a "Analyse All Positions" action that queues every position in the Portfolio for analysis.
2. WHEN Batch_Analysis is started, THE Portfolio_View SHALL run the TradingAgents pipeline concurrently using the same Worker_Pool as the Multi-Ticker Analysis view, dispatching up to Max_Concurrency positions simultaneously.
3. WHILE Batch_Analysis is running, THE Portfolio_View SHALL display a progress indicator showing the number of positions completed out of the total, and a separate progress tracker per active position.
4. WHILE Batch_Analysis is running, THE Portfolio_View SHALL inject the Ownership_Context for each position as specified in Requirement 5.
5. WHEN each position's analysis completes, THE Portfolio_View SHALL display the resulting decision (Buy / Overweight / Hold / Underweight / Sell) alongside the ticker in a results table.
6. WHEN Batch_Analysis is running, THE Portfolio_View SHALL allow the user to cancel all remaining and active analyses without affecting already-completed results.
7. IF a position's analysis fails, THEN THE Portfolio_View SHALL record the error for that position, display it in the results table, and SHALL continue analysing the remaining positions.
8. THE Batch_Analysis implementation SHALL reuse the Worker_Pool infrastructure extracted into `dashboard/worker_pool.py` (see cross-cutting-concerns.md) rather than implementing a separate queue-and-run mechanism, so that both the Multi-Ticker Analysis view and Portfolio view share the same execution infrastructure and do not diverge.
9. WHEN an analysis is initiated from the Portfolio_View (batch or individual), THE Dashboard SHALL save the Ownership_Context string into the `portfolio_context` field of the analysis JSON log (`full_states_log_<DATE>.json`) alongside the existing report fields, so that History can identify portfolio-aware runs.
10. WHEN the user removes a position from the Portfolio while Batch_Analysis is running, THE Portfolio_View SHALL display a warning: "Removing {ticker} from your portfolio will take effect after the current batch completes. The queued analysis for {ticker} will still run." THE Portfolio_View SHALL NOT remove the ticker from the active analysis queue.

---

### Requirement 7: Individual Position Analysis

**User Story:** As a trader, I want to drill into any single position for a full deep-dive analysis, so that I can get detailed agent reports for a specific holding.

#### Acceptance Criteria

1. THE Portfolio_View SHALL provide a per-position "Analyse" action that initiates Individual_Analysis for that position.
2. WHEN Individual_Analysis is initiated, THE Portfolio_View SHALL inject the Ownership_Context for the selected position as specified in Requirement 5. IF the Ownership_Context injection fails, THEN THE Portfolio_View SHALL block the analysis from starting and SHALL display a descriptive error to the user.
3. WHEN Individual_Analysis is running, THE Portfolio_View SHALL display the live agent progress pipeline (agent status indicators and log lines) consistent with the existing Single Ticker view. THE Portfolio_View SHALL show progress elements only after the analysis pipeline has begun executing, not before.
4. WHEN Individual_Analysis completes, THE Portfolio_View SHALL display the full set of agent reports using the shared `render_decision_first(data, container)` utility from `dashboard/utils.py` (see cross-cutting-concerns.md): Decision Banner → Key Metrics Row (Price Target, Time Horizon) → Executive Summary inline → analyst reports as individual collapsed `st.expander` widgets → Research Plan, Trader Plan, and Final Decision as expanders below. This layout SHALL be consistent with the improved Single Ticker view (not the legacy tabbed layout).
5. THE Portfolio_View SHALL allow the user to configure the analysis date, LLM provider, model selection, and analyst selection before initiating Individual_Analysis.
6. WHEN Individual_Analysis completes, THE Portfolio_View SHALL display an "💬 Open in Chat" button that navigates to the Analysis Chat view with that analysis pre-selected in Single_Mode.

---

### Requirement 8: Analysis Configuration

**User Story:** As a trader, I want to configure LLM provider, models, analysts, and concurrency for portfolio analyses, so that I can control cost and depth of analysis.

#### Acceptance Criteria

1. THE Portfolio_View SHALL expose sidebar controls for: LLM provider selection, deep-thinking model selection, quick-thinking model selection, analyst selection (market, social, news, fundamentals), analysis date, output language, and Max_Concurrency (for batch analysis).
2. THE Portfolio_View SHALL apply the same provider-to-model mapping used by the existing Watchlist view.
3. WHEN the user changes the LLM provider, THE Portfolio_View SHALL update the available model options to match that provider's supported models. WHEN the user changes the LLM provider, THE Portfolio_View SHALL preserve the user's currently selected model if that model is supported by the new provider, and SHALL fall back to the new provider's default model only if the previously selected model is not available.
4. THE Portfolio_View SHALL default analyst selection to market, news, and fundamentals, consistent with the existing Watchlist view defaults.
5. THE Portfolio_View SHALL expose a "Max concurrent analyses" slider with a range of 1 to 5 and a default value of 3, used when Batch_Analysis is running. THE slider SHALL be disabled while a batch is running.

---

### Requirement 9: Portfolio Data Schema Extensibility

**User Story:** As a developer, I want the portfolio JSON schema to accommodate future fields like cost basis and sector, so that I can extend the feature without breaking existing data.

#### Acceptance Criteria

1. THE Portfolio_Store SHALL read position objects tolerantly, ignoring unknown fields rather than raising an error, so that data written by a future version of the application can be read by the current version.
2. THE Portfolio_Store SHALL preserve all existing fields in a position object when updating only the `shares` field, applying the same tolerant unknown-field handling used during reads, so that future fields (e.g., `cost_basis`) added by a later version are not silently dropped on update.
3. THE Portfolio_Store SHALL store positions as a JSON array under a top-level `"positions"` key, and MAY include additional top-level metadata keys (e.g., `"schema_version"`) to support future migrations.

---

### Requirement 10: Portfolio-Aware Run Flag in Saved Logs (Gap 1)

**User Story:** As a user browsing History, I want to see which past analyses were run with portfolio ownership context, so that I can distinguish portfolio-aware recommendations from generic ones.

#### Acceptance Criteria

1. WHEN an analysis is initiated from the Portfolio_View with Ownership_Context injected, THE Dashboard SHALL pass the Ownership_Context string to the runner as a `portfolio_context` parameter.
2. THE runner SHALL write the `portfolio_context` string into the saved `full_states_log_<DATE>.json` file under the top-level key `"portfolio_context"`.
3. WHEN no Ownership_Context is injected, THE runner SHALL omit the `"portfolio_context"` key from the saved JSON entirely.
4. THE History view SHALL display a `"🏦 Portfolio run"` badge on any Run_Record whose saved JSON contains a non-empty `"portfolio_context"` field.
5. THE addition of the `"portfolio_context"` field SHALL NOT break any existing code that reads `full_states_log_<DATE>.json`.

---

### Requirement 11: Memory Log JSON Migration (Gap 4)

**User Story:** As a developer, I want the trading memory log stored as JSON so that all dashboard features reading return data are reliable and not dependent on a fragile markdown parser.

#### Acceptance Criteria

1. THE system SHALL maintain `~/.tradingagents/memory/trading_memory.json` as the authoritative data source alongside the existing `trading_memory.md` (retained for human readability only). Full specification is in the `memory-log-json-migration` spec.
2. THE `load_memory_entries()` helper SHALL read from `trading_memory.json` when it exists, falling back to parsing `trading_memory.md` only when the JSON file is absent.
3. ALL dashboard features that read return data SHALL use `load_memory_entries()` exclusively — no direct markdown parsing SHALL occur outside of `TradingMemoryLog`.

---

### Requirement 12: Dashboard Navigation and Import (Gap 6)

**User Story:** As a developer, I want the Portfolio view to be fully wired into the dashboard navigation so that it is accessible from the sidebar without any runtime errors.

#### Acceptance Criteria

1. THE `streamlit_app.py` file SHALL import `render_portfolio` from `dashboard/views/portfolio.py`.
2. THE `_NAV_OPTIONS` list in `streamlit_app.py` SHALL include `"💼 Portfolio"` after `"📊 Multi-Ticker Analysis"`.
3. THE routing block in `streamlit_app.py` SHALL add a case `elif view == "💼 Portfolio": render_portfolio()`.
4. THE `streamlit_app.py` file SHALL rename the existing `"📋 Watchlist"` entry to `"📊 Multi-Ticker Analysis"` in `_NAV_OPTIONS` and update its routing case accordingly.

---

### Requirement 13: Portfolio Overview Clickable Last-Analysis Badge (Gap 9)

**User Story:** As a trader, I want to click on a position's last analysis rating in the Portfolio Overview and jump directly to that run in History, so that I can review the full analysis without manually searching for it.

#### Acceptance Criteria

1. WHEN a position in the Portfolio_Overview has a Last_Analysis_Badge (a saved analysis exists for that ticker), THE Portfolio_Overview SHALL render the badge as a clickable element.
2. WHEN the user clicks a Last_Analysis_Badge, THE Portfolio_View SHALL set `st.session_state["hist_ticker_filter"]` to the ticker symbol, set `st.session_state["_nav_target"]` to `"📜 History"`, and call `st.rerun()`.
3. THE History_View SHALL read `st.session_state["hist_ticker_filter"]` on load and pre-populate the Ticker_Search_Input with that value, then clear the key from session state after consuming it.

---

### Requirement 14: `run_analysis()` Portfolio Context Parameter (Gap 8)

**User Story:** As a developer, I want `run_analysis()` to accept an optional `portfolio_context` parameter so that portfolio-aware analyses can be flagged in the saved JSON log.

#### Acceptance Criteria

1. THE `run_analysis()` function in `dashboard/runner.py` SHALL accept an optional `portfolio_context: Optional[str] = None` parameter.
2. WHEN `portfolio_context` is provided and non-empty, THE `_worker()` function SHALL patch the saved `full_states_log_<DATE>.json` file after `_log_state()` writes it, adding the `"portfolio_context"` key with the provided string value.
3. WHEN `portfolio_context` is `None` or empty, THE `_worker()` function SHALL NOT add the `"portfolio_context"` key to the saved JSON.
4. ALL callers of `run_analysis()` in the Portfolio_View SHALL pass the Ownership_Context string as `portfolio_context` when initiating an analysis for a held ticker.
5. ALL callers of `run_analysis()` in the Single_Ticker_View, Multi-Ticker_Analysis_View, and any other view SHALL pass `portfolio_context=None` (the default) so existing behavior is unchanged.
