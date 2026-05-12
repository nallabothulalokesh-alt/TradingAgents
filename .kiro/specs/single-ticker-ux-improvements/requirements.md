# Requirements Document

## Introduction

This document covers three targeted UX improvements to the Single Ticker Deep Dive view in the TradingAgents Streamlit dashboard (`dashboard/views/single_ticker.py`). The improvements address: (1) making run progress more visible and informative while an analysis is executing, (2) restructuring the results layout so the most important information is immediately visible without scrolling or clicking, and (3) adding real-time ticker validation as the user types rather than waiting for the Run button.

No changes are made to the underlying agent pipeline, LangGraph graph, `RunState` class interface, or any backend logic. All changes are confined to the UI rendering layer in `dashboard/views/single_ticker.py` and minor additions to `dashboard/utils.py`.

**Dependencies:** Bug fixes 4 (RunState thread safety) and 17 (time.sleep replacement) must be completed first. The `compute_conviction()` shared utility (extracted per history-ux-improvements spec Req 9) should be implemented concurrently or before this spec.

## Glossary

- **Dashboard**: The TradingAgents Streamlit web application.
- **Single_Ticker_View**: The `render_single_ticker()` function and all helpers in `dashboard/views/single_ticker.py`.
- **RunState**: The thread-safe container class in `dashboard/utils.py` that tracks agent statuses, log lines, reports, and run lifecycle. Its public interface MUST NOT be changed.
- **Agent_Status**: A string value held in `RunState.agent_status` for each agent; one of `pending`, `running`, `done`, `error`, or `reused`.
- **Progress_Section**: The UI region rendered by `_render_progress()` that shows agent pipeline state during a live run.
- **Results_Section**: The UI region rendered by `_render_reports()` that shows the final decision and analyst reports.
- **Ticker_Input**: The `st.text_input` widget in the sidebar where the user types a ticker symbol.
- **Validation_Service**: The existing `validate_ticker()` function in `dashboard/utils.py` that calls yfinance to confirm a ticker is tradeable.
- **Debounce_Guard**: A session-state timestamp used to prevent the Validation_Service from being called more than once per debounce interval.
- **Decision_Banner**: The colored HTML block that displays the final rating (Buy / Overweight / Hold / Underweight / Sell).
- **Key_Metrics_Row**: The row of metric cards showing Price Target, Time Horizon, and Conviction directly below the Decision_Banner.
- **Executive_Summary**: A short plain-text paragraph extracted from the final trade decision report.
- **Analyst_Reports_Section**: The collapsible area containing the four analyst reports (Market, Social, News, Fundamentals).
- **Decision_Pipeline_Section**: The collapsible area containing the Research Decision, Trader Plan, and Final Decision reports.
- **Timeline_Stepper**: A sequential visual component that shows each agent as a step, lighting up as the agent starts and completing when it finishes.
- **Live_Log_Panel**: A scrollable text area that streams `RunState.log_lines` in real time during a run.
- **Overall_Progress_Bar**: A `st.progress` bar whose value equals the fraction of agents in `done` or `reused` status out of the total expected agents.
- **AGENT_TEAMS**: The ordered dict in `dashboard/utils.py` that defines team names and their member agents.
- **Session_State**: Streamlit's `st.session_state` dict, which persists values across script re-runs within a browser session.

---

## Requirements

### Requirement 1: Overall Progress Bar

**User Story:** As a trader running an analysis, I want to see a progress bar showing overall pipeline completion, so that I can immediately gauge how far along the run is without reading individual agent statuses.

#### Acceptance Criteria

1. WHEN a live analysis run is active (`RunState.running` is `True`), THE Single_Ticker_View SHALL render an Overall_Progress_Bar above the Timeline_Stepper.
2. THE Overall_Progress_Bar SHALL display a value equal to the count of agents whose Agent_Status is `done` or `reused` divided by the total count of expected agents for the current run configuration.
3. WHEN all expected agents have reached `done` or `reused` status, THE Overall_Progress_Bar SHALL display a value of 1.0 (100%), based on the actual agent count calculation regardless of any completion flags.
4. WHEN no agents have started yet (all statuses are `pending`), THE Overall_Progress_Bar SHALL display a value of 0.0.
5. THE Single_Ticker_View SHALL display a text label alongside the Overall_Progress_Bar showing the count in the format `"{done_count} / {total_count} agents complete"`.
6. WHEN a run completes successfully and `total_count` is greater than zero, THE Single_Ticker_View SHALL retain the Overall_Progress_Bar at 100% until the user initiates a new run or resets the view.
7. WHEN a run completes successfully and `total_count` is zero, THE Single_Ticker_View SHALL NOT render the Overall_Progress_Bar.
8. WHEN a run is loaded from cache (`from_cache` is `True`), THE Single_Ticker_View SHALL NOT render the Overall_Progress_Bar.

**Implementation Note:** `total_count` SHALL be derived as `len(run_state.agent_status)` — the number of keys in the `agent_status` dict built by `build_agent_status()`. This dict already accounts for selected analysts and all fixed pipeline agents (researchers, trader, risk team, portfolio manager). The count varies based on analyst selection (e.g., 3 analysts selected = 10 total agents; 4 analysts = 11).

---

### Requirement 2: Timeline Stepper

**User Story:** As a trader, I want to see each agent light up in sequence as it starts and completes, so that I can follow the pipeline step by step and know exactly which agent is working right now.

#### Acceptance Criteria

1. WHEN a live analysis run is active or has just completed, THE Single_Ticker_View SHALL render a Timeline_Stepper that lists every expected agent in pipeline order as defined by AGENT_TEAMS.
2. THE Timeline_Stepper SHALL display each agent as a distinct step with the agent's full name visible.
3. WHEN an agent's Agent_Status is `pending`, THE Timeline_Stepper SHALL render that step with a neutral (grey) color and a pending icon (⏳).
4. WHEN an agent's Agent_Status is `running`, THE Timeline_Stepper SHALL render that step with a highlighted (blue) color and a running icon (🔄), making it visually distinct from all other steps. The color used for display MAY differ from the status-derived default if overridden for display purposes.
5. WHEN an agent's Agent_Status is `done`, THE Timeline_Stepper SHALL render that step with a success (green) color and a completion icon (✅). The color used for display MAY differ from the status-derived default if overridden for display purposes.
6. WHEN an agent's Agent_Status is `reused`, THE Timeline_Stepper SHALL render that step with a purple color and a reused icon (📦).
7. WHEN an agent's Agent_Status is `error`, THE Timeline_Stepper SHALL render that step with a red color and an error icon (❌).
8. THE Timeline_Stepper SHALL display every agent that belongs to a selected analyst team; selected analyst agents SHALL always appear as steps and unselected analyst agents SHALL never appear as steps, regardless of their Agent_Status.
9. WHEN a run is loaded from cache (`from_cache` is `True`), THE Single_Ticker_View SHALL NOT render the Timeline_Stepper.

---

### Requirement 3: Live Log Panel

**User Story:** As a trader, I want to see a live log stream of what is happening right now during a run, so that I can understand what the agents are doing and diagnose slow or stuck runs.

#### Acceptance Criteria

1. WHEN a live analysis run is active (`RunState.running` is `True`), THE Single_Ticker_View SHALL render a Live_Log_Panel in the main content area.
2. THE Live_Log_Panel SHALL display all lines currently in `RunState.log_lines`, with the most recent line at the bottom.
3. THE Live_Log_Panel SHALL have a fixed maximum visible height so it does not push other content off screen; the panel SHALL allow unlimited log lines with scrolling so no log content is lost.
4. WHEN new log lines are appended to `RunState.log_lines` between Streamlit re-runs, THE Live_Log_Panel SHALL display the updated lines on the next re-run.
5. WHEN a run completes or fails, THE Single_Ticker_View SHALL hide the Live_Log_Panel and replace it with the Results_Section.
6. WHEN `RunState.log_lines` is empty during an active run, THE Live_Log_Panel SHALL display the placeholder text `"Waiting for agents to start…"`.
7. WHEN a run is loaded from cache (`from_cache` is `True`), THE Single_Ticker_View SHALL NOT render the Live_Log_Panel.

---

### Requirement 4: Prominent Progress Section Layout

**User Story:** As a trader, I want the progress section to be the dominant element on screen while a run is active, so that I am never confused about whether the analysis is still running.

#### Acceptance Criteria

1. WHEN a live analysis run is active, THE Single_Ticker_View SHALL render the Progress_Section (Overall_Progress_Bar + Timeline_Stepper + Live_Log_Panel) as the primary content block, occupying the full main-column width. IF the Progress_Section cannot render due to a technical failure, THEN THE Single_Ticker_View SHALL display a fallback message `"Progress display unavailable — run is still active"` in place of the Progress_Section.
2. THE Single_Ticker_View SHALL NOT render the Results_Section in a side-by-side column layout while a run is active; the Results_Section SHALL appear below the Progress_Section in a single-column layout.
3. WHEN a run is active and partial reports are available in `RunState.reports`, THE Single_Ticker_View SHALL render those partial reports below the Progress_Section so the user can read completed work while the run continues.
4. WHILE a run is active, THE Single_Ticker_View SHALL auto-refresh the page at an interval of no more than 2 seconds so that progress updates are visible without manual interaction. Auto-refresh reruns SHALL NOT trigger ticker validation (see Requirement 7 AC 11).

**Implementation Note (browser refresh edge case):** If the user refreshes the browser page (F5) while a run is active, the Streamlit session is destroyed and recreated. The background thread continues running (daemon threads are not killed by session destruction) but the RunState object in the old session is lost. The new session will show the idle state. The background thread will complete and save results to disk, but the UI won't reflect it until the user manually runs the analysis again (at which point it will load from cache). This is acceptable behavior — the `time.sleep(2); st.rerun()` pattern used for auto-refresh should NOT be replaced with a blocking sleep that degrades server performance for other users. Consider using `st.fragment` with `run_every=2` (Streamlit 1.33+) as a non-blocking alternative if available.

---

### Requirement 5: Decision-First Results Layout

**User Story:** As a trader reviewing completed analysis, I want to see the final decision and key metrics immediately at the top of the page, so that I can understand the recommendation without scrolling or clicking any tabs.

#### Acceptance Criteria

1. WHEN analysis results are available (run complete or loaded from cache), THE Single_Ticker_View SHALL render the Decision_Banner as the first element in the Results_Section, before any analyst reports.
2. THE Decision_Banner SHALL display the rating text (Buy / Overweight / Hold / Underweight / Sell) in a large, bold font with a background color corresponding to the rating as defined in `RATING_COLORS`.
3. WHEN the final trade decision text contains a `**Price Target**` field, THE Single_Ticker_View SHALL display the extracted value in the Key_Metrics_Row. The extraction regex SHALL be case-insensitive: `(?i)\*\*Price\s+Target\*\*[:\s]*([^\n]+)`.
4. WHEN the final trade decision text contains a `**Time Horizon**` field, THE Single_Ticker_View SHALL display the extracted value in the Key_Metrics_Row. The extraction regex SHALL be case-insensitive: `(?i)\*\*Time\s+Horizon\*\*[:\s]*([^\n]+)`.
5. THE Single_Ticker_View SHALL always display the Conviction metric in the Key_Metrics_Row, derived from the `_conviction()` helper.
6. THE Key_Metrics_Row SHALL be rendered directly below the Decision_Banner with no intervening content.
7. WHEN the final trade decision text contains an `**Executive Summary**` field, THE Single_Ticker_View SHALL display the extracted text in a visible block directly below the Key_Metrics_Row, without requiring the user to expand any section.
8. IF the final trade decision text does not contain a `**Price Target**` or `**Time Horizon**` field, THEN THE Single_Ticker_View SHALL omit those cards from the Key_Metrics_Row; remaining cards SHALL reflow naturally to fill the available space without leaving empty placeholders.

---

### Requirement 6: Collapsible Analyst Reports

**User Story:** As a trader, I want the detailed analyst reports to be accessible but not cluttering the top of the page, so that I can read them when I want without them obscuring the decision.

#### Acceptance Criteria

1. WHEN analysis results are available, THE Single_Ticker_View SHALL render the Analyst_Reports_Section below the Key_Metrics_Row and Executive_Summary.
2. THE Analyst_Reports_Section SHALL render each available analyst report (Market, Social, News, Fundamentals) as an individually collapsible `st.expander`, defaulting to collapsed.
3. WHEN an analyst report is not present in the current results, THE Single_Ticker_View SHALL NOT render an expander for that report.
4. THE Single_Ticker_View SHALL NOT use `st.tabs` for analyst reports; each report SHALL be a separate expander.
5. THE Decision_Pipeline_Section SHALL render below the Analyst_Reports_Section, with each of the Research Decision, Trader Plan, and Final Decision reports as individually collapsible expanders.
6. THE expander for the Final Decision report in the Decision_Pipeline_Section SHALL default to expanded so the full decision text is visible without a click.

**Migration Note (existing code):** The current `_render_reports()` function in `single_ticker.py` uses `st.tabs` for analyst reports (line ~230: `tabs = st.tabs([_SECTION_LABELS[s] for s in analyst_keys])`). This must be replaced with individual `st.expander` widgets. The Decision Pipeline section already uses expanders — no change needed there.

---

### Requirement 7: Real-Time Ticker Validation

**User Story:** As a trader entering a ticker symbol, I want to see inline validation feedback as I type, so that I know immediately whether the symbol is valid before clicking Run Analysis.

**Streamlit Execution Model Note:** Streamlit reruns the entire script on every widget interaction. There is no true "600ms after last keystroke" timer — each keystroke that changes the `st.text_input` value triggers a full rerun. The debounce is implemented by comparing timestamps across reruns: validate only when the ticker value has changed AND 600ms has elapsed since the last validation call.

#### Acceptance Criteria

1. WHEN the value of the Ticker_Input changes (differs from the last validated value) and the new value has at least 1 non-whitespace character, AND at least 600 milliseconds have elapsed since the last Validation_Service call, THE Single_Ticker_View SHALL trigger the Validation_Service.
2. THE Debounce_Guard SHALL be implemented using a `st.session_state` timestamp; the Validation_Service SHALL NOT be called if the time elapsed since the last call is less than 600 milliseconds.
3. WHEN the Validation_Service returns a valid result for the current Ticker_Input value, THE Single_Ticker_View SHALL display the message `"✅ {TICKER} — valid"` inline below the Ticker_Input widget.
4. WHEN the Validation_Service returns an invalid result for the current Ticker_Input value, THE Single_Ticker_View SHALL display the error message returned by `validate_ticker()` inline below the Ticker_Input widget.
5. THE inline validation feedback SHALL be rendered in the sidebar directly below the Ticker_Input widget, replacing any previously displayed validation message for that input.
6. WHEN the Ticker_Input is cleared (empty string), THE Single_Ticker_View SHALL clear any existing inline validation message and SHALL NOT call the Validation_Service.
7. WHEN a live analysis run is active (`RunState.running` is `True`), THE Single_Ticker_View SHALL NOT trigger real-time validation, as the Ticker_Input is disabled during a run.
8. WHEN the user clicks "Run Analysis" and the Ticker_Input value has already been validated successfully by the real-time validator, THE Single_Ticker_View SHALL use the cached validation result and SHALL NOT call the Validation_Service again for that ticker value, even if the cached result is older than the debounce interval.
9. WHEN the user clicks "Run Analysis" and no cached validation result exists for the current Ticker_Input value, THE Single_Ticker_View SHALL call the Validation_Service synchronously before proceeding, preserving existing behavior.
10. THE inline validation message SHALL NOT display price data, sector information, or any data beyond the confirmation that the ticker is valid or the reason it is invalid.
11. Auto-refresh cycles (during an active run) SHALL NOT trigger ticker validation — validation SHALL only be triggered when the Ticker_Input value actually changes between reruns.

---

### Requirement 8: Debounce State Management

**User Story:** As a developer maintaining the dashboard, I want the debounce logic to be implemented cleanly using Streamlit session state, so that it works correctly within Streamlit's full-script-rerun execution model.

#### Acceptance Criteria

1. THE Single_Ticker_View SHALL store the timestamp of the last Validation_Service call in `st.session_state` under a dedicated key (e.g., `"st_ticker_val_ts"`).
2. THE Single_Ticker_View SHALL store the last validated ticker string in `st.session_state` under a dedicated key (e.g., `"st_ticker_last_validated"`).
3. WHEN the current Ticker_Input value equals the value stored in `"st_ticker_last_validated"`, THE Single_Ticker_View SHALL NOT call the Validation_Service again, regardless of elapsed time.
4. WHEN the current Ticker_Input value differs from `"st_ticker_last_validated"` and the elapsed time since `"st_ticker_val_ts"` is less than 600 milliseconds, THE Single_Ticker_View SHALL NOT call the Validation_Service.
5. WHEN the current Ticker_Input value differs from `"st_ticker_last_validated"` and the elapsed time since `"st_ticker_val_ts"` is 600 milliseconds or more, THE Single_Ticker_View SHALL call the Validation_Service and update both `"st_ticker_val_ts"` and `"st_ticker_last_validated"` in `st.session_state`.
