# Requirements Document

## Introduction

This feature improves the user experience of the **Past Analyses** tab in the TradingAgents Streamlit dashboard's History view (`dashboard/views/history.py`). Three specific improvements are in scope:

1. **Decision-first layout** — when a user expands a run in the history list, the detail view is refactored to mirror the "decision first, details below" pattern already used in the Single Ticker view: a prominent decision banner, key metric cards, an executive summary, and then analyst reports and debate sections as collapsible expanders (not tabs).
2. **Ticker + date range search** — the filter row gains a free-text ticker search input and two date pickers (from / to) so users can quickly narrow the list without scrolling through a multiselect.
3. **Additional filters** — a return-based filter lets users show only resolved runs whose raw return meets a minimum and/or maximum threshold; pending runs (no return data yet) are unaffected by this filter unless the user explicitly excludes them.

The **Memory & Reflections** tab and all backend/agent pipeline code are explicitly out of scope and must not be changed.

**Dependencies:**
- Memory JSON migration spec must be completed first (Requirement 3's return filter depends on reliable `load_memory_entries()` from JSON).
- Bug fix 14 (`list_history_summary()`) should be implemented as part of this spec (Requirement 5 AC 1).
- Bug fix 6 (deduplication) should be implemented before this spec.
- The `compute_conviction()` shared utility (Requirement 9) is also used by Compare, Portfolio, and Multi-Ticker specs.

---

## Glossary

- **History_View**: The Streamlit page rendered by `dashboard/views/history.py`, containing the "📁 Past Analyses" and "🧠 Memory & Reflections" tabs.
- **Past_Analyses_Tab**: The "📁 Past Analyses" tab within the History_View; the only tab affected by this feature.
- **Run_Record**: A single saved analysis result returned by `list_history()`, containing fields: `ticker`, `date`, `decision`, `rating`, `file`, and `data` (full JSON).
- **Memory_Entry**: A single entry returned by `load_memory_entries()`, containing fields: `ticker`, `date`, `rating`, `raw` (raw return), `alpha`, `holding`, `reflection`, and `pending` (bool).
- **Resolved_Run**: A Run_Record whose ticker+date matches a Memory_Entry where `pending` is `False` and a numeric `raw` return value is present.
- **Pending_Run**: A Run_Record whose ticker+date either has no matching Memory_Entry, or matches a Memory_Entry where `pending` is `True`.
- **Decision_Banner**: A full-width colored HTML block displaying the rating (Buy / Overweight / Hold / Underweight / Sell) with the rating's associated color from `RATING_COLORS`.
- **Key_Metrics_Row**: A row of `st.metric` cards displayed beneath the Decision_Banner, showing Price Target, Time Horizon, and optionally Conviction level.
- **Executive_Summary**: A styled text block extracted from the `**Executive Summary**` field of `final_trade_decision`, displayed inline (no expander required).
- **Filter_Bar**: The row of filter and sort controls at the top of the Past_Analyses_Tab.
- **Ticker_Search_Input**: A free-text `st.text_input` widget in the Filter_Bar for filtering runs by ticker symbol substring.
- **Date_Range_Filter**: A pair of `st.date_input` widgets ("From" and "To") in the Filter_Bar for filtering runs by analysis date.
- **Rating_Filter**: The existing `st.multiselect` widget for filtering by rating; must be preserved unchanged.
- **Return_Filter**: A pair of `st.number_input` widgets for minimum and maximum raw return percentage, applied only to Resolved_Runs.
- **Run_Detail_Panel**: The content rendered inside a `st.expander` when a user expands a Run_Record row.
- **RATING_COLORS**: The dict defined in `dashboard/utils.py` mapping rating strings to hex color codes.
- **RATING_ORDER**: The list `["Buy", "Overweight", "Hold", "Underweight", "Sell"]` defined in `dashboard/utils.py`.
- **sanitize_report**: The helper function in `dashboard/utils.py` that strips tool-call markup from report text.

---

## Requirements

### Requirement 1: Decision-First Layout in Run Detail Panel

**User Story:** As a user reviewing past analyses, I want the expanded run detail to show the decision prominently at the top with key metrics and a summary visible immediately, so that I can assess the outcome at a glance without scrolling through tabs.

#### Acceptance Criteria

1. WHEN a user expands a Run_Record row in the Past_Analyses_Tab, THE Run_Detail_Panel SHALL display the Decision_Banner as the first visible element, before any other content.
2. THE Decision_Banner SHALL display the rating text (e.g. "Final Decision: Buy") in the color defined by `RATING_COLORS` for that rating, with a matching semi-transparent background and border, at a font size of at least 18px.
3. WHEN the `final_trade_decision` text contains a `**Price Target**` field, THE Run_Detail_Panel SHALL display the extracted price target value in a `st.metric` card in the Key_Metrics_Row.
4. WHEN the `final_trade_decision` text contains a `**Time Horizon**` field, THE Run_Detail_Panel SHALL display the extracted time horizon value in a `st.metric` card in the Key_Metrics_Row.
5. WHEN the `final_trade_decision` text contains an `**Executive Summary**` field, THE Run_Detail_Panel SHALL display the extracted executive summary text in a styled inline block beneath the Key_Metrics_Row, without requiring the user to expand any additional widget.
6. THE Run_Detail_Panel SHALL display the shortcut buttons ("💬 Open in Chat" and "🔄 Run Again") beneath the Executive_Summary block (or beneath the Key_Metrics_Row if no executive summary is present).
7. THE Run_Detail_Panel SHALL display each available analyst report (market, news, fundamentals, social sentiment) as a separate `st.expander` with a descriptive label, replacing the current `st.tabs` implementation for analyst reports.
8. WHEN an analyst report section is absent from the run data, THE Run_Detail_Panel SHALL omit that section's expander entirely, and SHALL still display expanders for all other available analyst report sections individually.
9. THE Run_Detail_Panel SHALL display the Research Debate, Trader Plan, Risk Management Debate, and Final Portfolio Manager Decision as `st.expander` widgets below the analyst report expanders, in that order.
10. THE Run_Detail_Panel SHALL render the Final Portfolio Manager Decision expander in an expanded state by default, and all other expanders in a collapsed state by default.
11. IF the `final_trade_decision` field is absent from the run data, THEN THE Run_Detail_Panel SHALL omit the Decision_Banner, Key_Metrics_Row, and Executive_Summary block, and display a placeholder message indicating no decision is available.

---

### Requirement 2: Ticker Text Search and Date Range Filter

**User Story:** As a user with many saved analyses, I want to type a ticker symbol and pick a date range to quickly narrow the list, so that I can find specific runs without scrolling through a long multiselect.

#### Acceptance Criteria

1. THE Filter_Bar SHALL contain a Ticker_Search_Input widget that accepts free-text entry of a ticker symbol or partial ticker symbol.
2. WHEN the Ticker_Search_Input contains one or more characters, THE Past_Analyses_Tab SHALL display only Run_Records whose `ticker` field contains the entered text as a case-insensitive substring.
3. WHEN the Ticker_Search_Input is empty, THE Past_Analyses_Tab SHALL apply no ticker-based filtering (all tickers are shown).
4. THE Filter_Bar SHALL contain a Date_Range_Filter with a "From" date picker and a "To" date picker.
5. WHEN a "From" date is selected, THE Past_Analyses_Tab SHALL display only Run_Records whose `date` field is greater than or equal to the selected "From" date.
6. WHEN a "To" date is selected, THE Past_Analyses_Tab SHALL display only Run_Records whose `date` field is less than or equal to the selected "To" date.
7. WHEN both "From" and "To" dates are selected, THE Past_Analyses_Tab SHALL display only Run_Records whose `date` field falls within the inclusive range [From, To].
8. WHEN only one of "From" or "To" date is selected, THE Past_Analyses_Tab SHALL apply a one-sided filter (only "From" = show runs on or after that date; only "To" = show runs on or before that date). WHEN neither is selected, THE Past_Analyses_Tab SHALL apply no date-based filtering.
9. THE Filter_Bar SHALL retain the existing Rating_Filter multiselect widget without modification.
10. THE Filter_Bar SHALL retain the existing sort order selectbox without modification.
11. WHEN multiple filters are active simultaneously (Ticker_Search_Input, Date_Range_Filter, Rating_Filter), THE Past_Analyses_Tab SHALL display only Run_Records that satisfy all active filters (logical AND).
12. THE Past_Analyses_Tab SHALL display the count of currently visible runs after all filters are applied, updating immediately when any filter value changes.

---

### Requirement 3: Return-Based Filter for Resolved Runs

**User Story:** As a user tracking investment performance, I want to filter past analyses by their actual return outcome, so that I can review only the runs that met or exceeded a return threshold.

#### Acceptance Criteria

1. THE Filter_Bar SHALL contain a Return_Filter with a "Min Return (%)" number input and a "Max Return (%)" number input.
2. THE History_View SHALL join each Run_Record with its corresponding Memory_Entry by matching `ticker` and `date` fields to obtain the `raw` return value for Resolved_Runs.
3. WHEN a "Min Return (%)" value is entered, THE Past_Analyses_Tab SHALL exclude Resolved_Runs whose `raw` return value is strictly less than the entered minimum.
4. WHEN a "Max Return (%)" value is entered, THE Past_Analyses_Tab SHALL exclude Resolved_Runs whose `raw` return value is strictly greater than the entered maximum.
5. WHEN a Return_Filter value is entered, THE Past_Analyses_Tab SHALL continue to display all Pending_Runs regardless of the return filter values.
6. WHEN both "Min Return (%)" and "Max Return (%)" are entered and the minimum is greater than the maximum, THE Past_Analyses_Tab SHALL display a validation warning and SHALL apply no return-based filtering until valid (non-contradictory) values are entered.
7. WHEN neither "Min Return (%)" nor "Max Return (%)" is entered, THE Past_Analyses_Tab SHALL apply no return-based filtering.
8. WHEN a Return_Filter is active, THE Past_Analyses_Tab SHALL display the raw return value for each Resolved_Run in the summary table row, so users can see why a run was included or excluded.
9. IF a Run_Record matches a Memory_Entry where `pending` is `True`, THEN THE Past_Analyses_Tab SHALL treat that run as a Pending_Run and SHALL NOT apply the Return_Filter to it.
10. THE Return_Filter SHALL accept decimal values (e.g. 5.5 for 5.5%) and SHALL NOT restrict input to integers only.

---

### Requirement 4: Preserve Memory & Reflections Tab

**User Story:** As a user of the Memory & Reflections tab, I want that tab to remain exactly as it is, so that existing workflows are not disrupted by the history UX improvements.

#### Acceptance Criteria

1. THE History_View SHALL render the "🧠 Memory & Reflections" tab with identical content, layout, and behavior to the current implementation in all cases.
2. THE History_View SHALL NOT modify any logic, widgets, or data loading in the Memory & Reflections tab as part of this feature.

---

### Requirement 5: No Backend or Pipeline Changes

**User Story:** As a developer maintaining the agent pipeline, I want the history UX improvements to be confined to the dashboard layer, so that the backend logic remains stable and untouched.

#### Acceptance Criteria

1. THE History_View changes SHALL NOT modify `dashboard/utils.py` beyond: (a) adding a helper function to join Run_Records with Memory_Entries by ticker+date for the Return_Filter, (b) adding a `list_history_summary()` function that reads only lightweight fields (`company_of_interest`, `trade_date`, `final_trade_decision`, `portfolio_context`) without loading full report text, (c) moving `_conviction()` from `single_ticker.py` to `utils.py` as a public `compute_conviction(reports)` function, and (d) internal modifications to `list_history()` that preserve its existing function signature and return schema.

**Performance Note:** The current `list_history()` reads the ENTIRE JSON file for every saved analysis (including all report text — market, news, fundamentals, sentiment, debate histories, etc.). For 500+ analyses, this loads hundreds of megabytes into memory on every 30-second cache refresh. The new `list_history_summary()` function SHALL parse each JSON file but retain only the fields needed for the summary table (ticker, date, decision, rating, portfolio_context, file path), allowing the full file content to be garbage collected. The optimization is about memory retention, not disk I/O — each file must still be opened and parsed, but only ~5-10KB per record is kept in the cache vs. ~500KB-2MB for full data. The full `list_history()` function SHALL remain available for views that need complete data (e.g., Chat context building).
2. THE History_View changes SHALL NOT modify the `RunState` class in `dashboard/utils.py`.
3. THE History_View changes SHALL NOT modify any file outside of `dashboard/views/history.py`, `dashboard/utils.py`, and `dashboard/views/single_ticker.py` (the latter only to remove the private `_conviction()` function and replace it with a call to the shared `compute_conviction()`).
4. THE History_View changes SHALL NOT modify the `list_history()` function signature or its return schema.
5. THE History_View changes SHALL NOT modify the `load_memory_entries()` function signature or its return schema.
6. THE `list_history()` function SHALL deduplicate records by ticker+date, keeping the most recently modified file when duplicates exist, so that running the same ticker+date twice does not produce duplicate rows in the History view.

**Bug Fix Note (existing code):** The current `list_history()` in `dashboard/utils.py` iterates all `full_states_log_*.json` files and returns every one found. If a user runs NVDA on 2026-05-01 twice, both files appear as separate rows in History. The deduplication SHALL be implemented inside `list_history()` (internal change, same signature and return schema).

---

### Requirement 6: Portfolio-Aware Run Badge in History

**User Story:** As a user browsing past analyses, I want to see which runs were initiated from the Portfolio view with ownership context, so that I can distinguish portfolio-aware recommendations from generic ones.

#### Acceptance Criteria

1. WHEN a Run_Record's underlying JSON file contains a non-empty `portfolio_context` field, THE Past_Analyses_Tab SHALL display a "🏦 Portfolio run" badge alongside the ticker and date in the summary table row.
2. WHEN a Run_Record's underlying JSON file does not contain a `portfolio_context` field or the field is empty, THE Past_Analyses_Tab SHALL display no badge for that run.
3. WHEN a user expands a Run_Record that has a `portfolio_context` field, THE Run_Detail_Panel SHALL display the ownership context string (e.g. "Portfolio context: You currently hold 50 shares of NVDA.") in a styled block above the Decision_Banner.
4. THE `list_history()` helper SHALL include the `portfolio_context` field value (or `None` if absent) in each returned Run_Record dict so that the History_View can render the badge without re-reading the JSON file.

---

### Requirement 7: Trader Plan Key Name Compatibility

**User Story:** As a developer, I want the History view to correctly display the Trader Plan report for all saved analyses, including those saved before the key name was standardised.

#### Acceptance Criteria

1. WHEN rendering the Trader Plan expander in the Run_Detail_Panel, THE History_View SHALL read the trader plan content using the fallback expression `data.get("trader_investment_decision") or data.get("trader_investment_plan")` to handle both the legacy key name (`trader_investment_decision`) and the current key name (`trader_investment_plan`).
2. THE History_View SHALL NOT assume either key name is exclusively present — both SHALL be checked on every render.

**Bug Fix Note (existing code):** The current `_render_run_detail()` in `history.py` (line ~107) only checks `data.get("trader_investment_plan")`. Analyses saved before the key rename use `trader_investment_decision`, causing the Trader Plan expander to appear empty for those runs.

---

### Requirement 9: Conviction Helper Shared Utility

**User Story:** As a developer, I want the conviction level computation to be a shared utility function so that all views (Single Ticker, Compare, Portfolio, Multi-Ticker) use identical logic.

**Cross-references:** This utility is consumed by:
- `single-ticker-ux-improvements` spec Requirement 5 AC 5
- `compare-ux-improvements` spec Requirement 3 AC 9
- `portfolio-management` spec Requirement 7 AC 4
- `multi-ticker-analysis` spec Requirement 2 (key metrics row)

#### Acceptance Criteria

1. THE `_conviction()` function currently in `dashboard/views/single_ticker.py` SHALL be extracted and added to `dashboard/utils.py` as a public function named `compute_conviction(reports: dict) -> tuple[str, str]`.
2. THE `compute_conviction()` function SHALL accept a dict of report sections and return a tuple of `(label, hex_color)` where label is one of "High", "Medium", "Low".
3. THE `compute_conviction()` function SHALL use the same scoring logic: count how many of the 7 report sections (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`, `investment_plan`, `trader_investment_plan`, `final_trade_decision`) are non-empty; return "High" if score ≥ 6, "Medium" if score ≥ 4, else "Low".
4. THE Single_Ticker_View SHALL be updated to call `compute_conviction()` from `dashboard/utils.py` instead of the private `_conviction()` function.
5. THE Compare_View, Portfolio_View, and Multi-Ticker_Analysis_View SHALL all call `compute_conviction()` from `dashboard/utils.py`.

---

### Requirement 10: "Open in Multi-Chat" from History

**User Story:** As a user browsing History, I want to open any run directly into multi-analysis chat mode alongside other runs, so that I can start cross-analysis conversations without going to the Compare view first.

#### Acceptance Criteria

1. WHEN a user expands a Run_Record row in the Past_Analyses_Tab, THE Run_Detail_Panel SHALL display an "💬 Open in Multi-Chat" button alongside the existing "💬 Open in Chat" and "🔄 Run Again" buttons.
2. WHEN the user clicks "💬 Open in Multi-Chat", THE History_View SHALL set `st.session_state["chat_multi_prefill"]` to a list containing the Analysis_Key (`"{ticker}|{date}"`) for that run, set `st.session_state["chat_mode"]` to `"multi"`, set `st.session_state["_nav_target"]` to `"💬 Analysis Chat"`, and call `st.rerun()`.
3. THE Chat_View SHALL receive the prefill key and activate Multi_Mode with that analysis pre-selected, consistent with the behaviour specified in the analysis-chat-improvements spec Requirement 2 AC 10.

---

### Requirement 11: "Run Again" Button Prefills Both Ticker and Date

**User Story:** As a user clicking "Run Again" on a past analysis, I want both the ticker AND the analysis date to be pre-populated in the Single Ticker view, so that I can re-run the exact same analysis without manually setting the date.

#### Acceptance Criteria

1. WHEN the user clicks "🔄 Run Again" on a Run_Record, THE History_View SHALL set `st.session_state["st_ticker_validated"]` to the record's ticker symbol.
2. WHEN the user clicks "🔄 Run Again" on a Run_Record, THE History_View SHALL set `st.session_state["st_prefill_date"]` to the record's analysis date string (YYYY-MM-DD format).
3. THE Single_Ticker_View SHALL read `st.session_state["st_prefill_date"]` on load and use it as the default value for the date input widget, then clear the key from session state after consuming it.
4. WHEN `st.session_state["st_prefill_date"]` is not set, THE Single_Ticker_View SHALL default the date input to `date.today()`, preserving current behavior.

**Bug Fix Note (existing code):** The current "Run Again" button only sets `st_ticker_validated` (ticker) but not the date. The user must manually change the date input, which defaults to today. This is confusing when re-running a historical analysis.

---

### Requirement 12: "Open in Chat" Cache Invalidation During Active Batch

**User Story:** As a user clicking "Open in Chat" on a completed watchlist result while the batch is still running, I want the Chat view to find my analysis, so that I don't get a "not found" error or wrong analysis loaded.

#### Acceptance Criteria

1. WHEN the user clicks "💬 Open in Chat" on a completed Result in the Multi-Ticker Analysis view, THE Multi-Ticker_Analysis_View SHALL call `invalidate_history_cache()` before setting `_nav_target`, so that the Chat view's `list_history()` call picks up the newly saved analysis file.
2. THE `invalidate_history_cache()` call SHALL happen per-result (when the user clicks the button), not only at batch completion.

**Bug Fix Note (existing code):** The current code calls `invalidate_history_cache()` only when the entire batch completes (inside `_start_next()` when queue is empty). If a user clicks "Open in Chat" on an early result while the batch is still running, the history cache may not yet include that result, causing the Chat view to fail to find it.
