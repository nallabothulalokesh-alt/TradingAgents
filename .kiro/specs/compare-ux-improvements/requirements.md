# Requirements Document

## Introduction

This feature improves the "Compare Analyses" view in the TradingAgents Streamlit dashboard (`dashboard/views/compare.py`). The current view allows users to pick two saved analyses and view them side by side, but the UX has several gaps: reports are buried in tabs, the dropdown is hard to navigate with many saved analyses, the comparison summary is minimal, there is no way to open both analyses together in chat, and the executive summary requires clicking into a tab to read. These five targeted improvements address each gap while preserving all existing behavior (mini price chart, verdict banner logic, Chat about A/B buttons, backend pipeline).

All changes are confined to `dashboard/views/compare.py`.

**Dependencies:** The `compute_conviction()` shared utility (from history-ux-improvements spec Req 9) must be available in `dashboard/utils.py` before this spec is implemented.

---

## Glossary

- **Compare_View**: The Streamlit page rendered by `render_compare()` in `dashboard/views/compare.py`.
- **Analysis_Record**: A saved analysis result loaded from disk via `list_history()`, containing fields such as `ticker`, `date`, `rating`, and `data` (the full JSON state).
- **Analysis_A / Analysis_B**: The two analyses selected by the user for side-by-side comparison.
- **Side_Panel**: One of the two `st.columns` rendered by `_render_side()` — either the left (A) or right (B) column.
- **Ticker_Filter**: A text input widget placed above a dropdown that filters the dropdown options by ticker symbol substring.
- **Verdict_Banner**: The existing `<div>` element that displays "A is more bullish", "B is more bullish", or "Same rating" above the side-by-side columns.
- **Comparison_Table**: A new structured table rendered below the Verdict_Banner showing both analyses side by side across multiple dimensions.
- **Executive_Summary**: The text extracted from the `**Executive Summary**` field in `final_trade_decision`, displayed inline without requiring any user interaction.
- **Conviction_Level**: A derived label (High / Medium / Low) computed by counting how many of the 7 report sections are present in an analysis, using the same `_conviction()` logic as the Single Ticker view.
- **Expander**: A Streamlit `st.expander` widget that is collapsed by default and expands on click.
- **Chat_View**: The Streamlit page rendered by the Analysis Chat view, navigated to by setting `st.session_state["_nav_target"] = "💬 Analysis Chat"`.
- **Multi_Mode**: A multi-analysis chat mode in the Chat_View, activated by setting `st.session_state["chat_mode"] = "multi"`.
- **Analysis_Key**: A string identifier for a saved analysis, composed as `"{ticker}|{date}"`, used to pre-populate the Chat_View.
- **RATING_ORDER**: The ordered list `["Buy", "Overweight", "Hold", "Underweight", "Sell"]` imported from `dashboard.utils`.
- **RATING_COLORS**: The dict mapping rating strings to hex color codes, imported from `dashboard.utils`.

---

## Requirements

### Requirement 1: Replace Report Tabs with Collapsible Expanders

**User Story:** As a user comparing two analyses, I want each report section to be in a collapsible expander (collapsed by default) so that the page is not overwhelmed with content and I can expand only the sections I care about.

#### Acceptance Criteria

1. THE `_render_side` function SHALL render each available report section using `st.expander` instead of `st.tabs`.
2. WHEN `_render_side` renders report expanders, THE Compare_View SHALL render all expanders in a collapsed state by default (i.e., `expanded=False`).
3. THE `_render_side` function SHALL render report sections in the following order: Market, News, Fundamentals, Sentiment, Research Plan, Trader, Final Decision — matching the existing tab order.
4. WHEN a report section's content is an empty string or `None`, THE `_render_side` function SHALL omit that section's expander entirely.
5. THE `_render_side` function SHALL pass each report section's content through `sanitize_report()` before rendering it inside the expander.
6. WHEN `_render_side` renders report sections, THE Compare_View SHALL use `st.expander` as the sole rendering method — if expanders cannot be rendered, THE Compare_View SHALL display an error message rather than falling back to `st.tabs`.
7. THE Compare_View SHALL preserve the mini price chart, rating banner, and key metrics (Price Target, Time Horizon) rendering in `_render_side` where those elements are available; IF any of those elements cannot be preserved, THE Compare_View SHALL still proceed with the expander transition and render the remaining elements normally.

---

### Requirement 2: Ticker Search Filter Above Each Analysis Dropdown

**User Story:** As a user with many saved analyses, I want a text input above each dropdown that filters the options by ticker symbol so that I can quickly find the analysis I want without scrolling through a long flat list.

#### Acceptance Criteria

1. THE Compare_View SHALL render a text input widget above the Analysis A dropdown that accepts a ticker substring as a filter value.
2. THE Compare_View SHALL render a separate, independent text input widget above the Analysis B dropdown that accepts a ticker substring as a filter value.
3. WHEN the user types a value into the Analysis A filter input, THE Compare_View SHALL filter the Analysis A dropdown options to only include entries whose ticker symbol contains the filter value as a case-insensitive substring.
4. WHEN the user types a value into the Analysis B filter input, THE Compare_View SHALL filter the Analysis B dropdown options to only include entries whose ticker symbol contains the filter value as a case-insensitive substring.
5. WHEN the filter input for Analysis A is empty, THE Compare_View SHALL show all available analysis options in the Analysis A dropdown.
6. WHEN the filter input for Analysis B is empty, THE Compare_View SHALL show all available analysis options in the Analysis B dropdown.
7. THE Compare_View SHALL store the Analysis A filter value in `st.session_state` under a dedicated key (e.g., `"cmp_filter_a"`) so that the filter persists across reruns.
8. THE Compare_View SHALL store the Analysis B filter value in `st.session_state` under a dedicated key (e.g., `"cmp_filter_b"`) so that the filter persists across reruns.
9. WHEN the filter for Analysis A produces zero matching options, THE Compare_View SHALL display an informational message (e.g., "No analyses match this filter") and SHALL NOT render the Analysis A dropdown.
10. WHEN the filter for Analysis B produces zero matching options, THE Compare_View SHALL display an informational message (e.g., "No analyses match this filter") and SHALL NOT render the Analysis B dropdown.
11. THE Compare_View SHALL render the filter inputs and dropdowns for Analysis A and Analysis B in two side-by-side columns, maintaining the existing two-column layout.
12. WHEN the previously selected analysis for A or B is no longer in the filtered list (because the filter hides it), THE Compare_View SHALL display an info message: "Previously selected analysis is hidden by the current filter" and SHALL NOT auto-select a different analysis. The comparison SHALL not render until the user either clears the filter or selects a new analysis from the filtered list.

**Implementation Note (Streamlit selectbox limitation):** Streamlit's `st.selectbox` resets its selection when the options list changes (because the widget key's identity is tied to the options). To avoid losing the user's selection when they type in the filter: (1) use a stable `key` for each selectbox, (2) compute the `index` parameter dynamically based on the current session state selection, and (3) if the previously selected option is no longer in the filtered list, default to index 0. The filter text input and selectbox MUST use separate widget keys so they don't interfere with each other.

---

### Requirement 3: Richer Comparison Summary Table

**User Story:** As a user comparing two analyses, I want a structured side-by-side table below the verdict headline that shows rating, price target, time horizon, and conviction level for both analyses so that I can quickly assess the key differences without reading full reports.

#### Acceptance Criteria

1. THE Compare_View SHALL render the existing Verdict_Banner headline ("A is more bullish" / "B is more bullish" / "Same rating") above the Comparison_Table, preserving the existing verdict logic exactly.
2. THE Compare_View SHALL render a Comparison_Table below the Verdict_Banner that contains one row for each of the following dimensions: Rating, Price Target, Time Horizon, Conviction.
3. THE Comparison_Table SHALL display the value for Analysis_A in one column and the value for Analysis_B in a second column, with a row label in a third column.
4. WHEN rendering the Rating row, THE Comparison_Table SHALL display the rating string for each analysis using the corresponding color from RATING_COLORS.
5. WHEN a Price Target value is present in `final_trade_decision` (matched via `\*\*Price Target\*\*[:\s]+([^\n]+)`), THE Comparison_Table SHALL display it in the Price Target row for the corresponding analysis.
6. IF a Price Target value is absent from `final_trade_decision`, THEN THE Comparison_Table SHALL display "—" in the Price Target row for that analysis.
7. WHEN a Time Horizon value is present in `final_trade_decision` (matched via `\*\*Time Horizon\*\*[:\s]+([^\n]+)`), THE Comparison_Table SHALL display it in the Time Horizon row for the corresponding analysis.
8. IF a Time Horizon value is absent from `final_trade_decision`, THEN THE Comparison_Table SHALL display "—" in the Time Horizon row for that analysis.
9. THE Compare_View SHALL compute the Conviction_Level for each analysis using `compute_conviction()` from `dashboard/utils.py` (as specified in history-ux-improvements spec Req 9): count how many of the 7 report sections (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`, `investment_plan`, `trader_investment_plan`, `final_trade_decision`) are present; return "High" if score ≥ 6, "Medium" if score ≥ 4, else "Low".
10. THE Comparison_Table SHALL display the Conviction_Level for each analysis in the Conviction row, using the corresponding conviction color (High = `#22c55e`, Medium = `#f59e0b`, Low = `#ef4444`).
11. THE Compare_View SHALL render the Comparison_Table between the Verdict_Banner and the side-by-side Side_Panels.

---

### Requirement 4: "Compare Both in Chat" Button

**User Story:** As a user who has selected two analyses, I want a "Compare both in Chat" button that opens both analyses together in the multi-analysis chat mode so that I can ask questions about both analyses simultaneously.

#### Acceptance Criteria

1. WHEN two different analyses are selected (Analysis_A ≠ Analysis_B), THE Compare_View SHALL render a "Compare both in Chat" button in the chat shortcuts row alongside the existing "Chat about A" and "Chat about B" buttons.
2. WHEN the user clicks the "Compare both in Chat" button, THE Compare_View SHALL set `st.session_state["chat_multi_prefill"]` to a list containing the Analysis_Key for Analysis_A and the Analysis_Key for Analysis_B, where each Analysis_Key is formatted as `"{ticker}|{date}"`.
3. WHEN the user clicks the "Compare both in Chat" button, THE Compare_View SHALL set `st.session_state["chat_mode"]` to `"multi"`.
4. WHEN the user clicks the "Compare both in Chat" button, THE Compare_View SHALL set `st.session_state["_nav_target"]` to `"💬 Analysis Chat"`.
5. WHEN the user clicks the "Compare both in Chat" button, THE Compare_View SHALL call `st.rerun()` to trigger navigation to the Chat_View.
6. THE Compare_View SHALL NOT modify or remove the existing "Chat about A" and "Chat about B" buttons or their session state logic.
7. THE Compare_View SHALL render the three chat buttons ("Chat about A", "Chat about B", "Compare both in Chat") in a single row using `st.columns`.
8. WHEN Analysis_A and Analysis_B are the same (i.e., the same-selection warning is shown), THE Compare_View SHALL NOT render the "Compare both in Chat" button.
9. WHEN Analysis_A and Analysis_B have the same ticker AND same date but are different selections (possible if deduplication is not applied to the dropdown), THE Compare_View SHALL display a notice: "These are two runs of the same analysis — differences reflect model variability." and SHALL still render the comparison normally.

---

### Requirement 5: Executive Summary Visible Inline

**User Story:** As a user comparing two analyses, I want the executive summary for each analysis to be visible inline below the rating banner and key metrics, without requiring me to click into any tab or expander, so that I can immediately understand the key takeaway for each side.

#### Acceptance Criteria

1. THE `_render_side` function SHALL extract the Executive_Summary from `final_trade_decision` using the regex pattern `\*\*Executive Summary\*\*[:\s]+([^\n]+)`.
2. WHEN an Executive_Summary is found, THE `_render_side` function SHALL render it inline below the key metrics (Price Target / Time Horizon) and above the report expanders, without requiring any user interaction.
3. THE `_render_side` function SHALL render the Executive_Summary in a styled container (e.g., a dark-background `<div>` with a bold "Executive Summary" label), consistent with the pattern used in the Single Ticker view.
4. IF no Executive_Summary is found in `final_trade_decision`, THEN THE `_render_side` function SHALL NOT render any Executive Summary container for that side.
5. THE `_render_side` function SHALL render the Executive_Summary after the Price Target / Time Horizon metrics row and before the first report expander.
6. THE Compare_View SHALL render the Executive_Summary for both Analysis_A and Analysis_B independently — the presence or absence of an Executive_Summary on one side SHALL NOT affect the other side.

---

### Requirement 6: Trader Plan Key Name Compatibility

**User Story:** As a developer, I want the Compare view to correctly display the Trader Plan for all saved analyses regardless of which key name was used when the file was saved.

#### Acceptance Criteria

1. WHEN rendering the Trader Plan expander in `_render_side()`, THE Compare_View SHALL read the trader plan content using the fallback expression `data.get("trader_investment_decision") or data.get("trader_investment_plan")` to handle both the legacy key name (`trader_investment_decision`) and the current key name (`trader_investment_plan`).
2. THE Compare_View SHALL NOT assume either key name is exclusively present — both SHALL be checked on every render.

**Bug Fix Note (existing code):** The current `_render_side()` in `compare.py` only checks one key name. Analyses saved before the key rename will show an empty Trader section.
