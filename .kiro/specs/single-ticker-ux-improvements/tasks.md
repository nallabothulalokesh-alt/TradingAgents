# Tasks — Sprint 3: UX Improvements (Single Ticker, History, Compare)

## Single Ticker UX

### Task 1: Overall progress bar
- [ ] Add `st.progress(done_count / total_count)` above the agent pipeline section
- [ ] Calculate from `agent_status` dict: done + reused vs total
- [ ] Show text: "3/9 agents complete"

### Task 2: Timeline stepper visualization
- [ ] Replace the current column-based progress with a horizontal stepper showing pipeline phases
- [ ] Phases: Analysts (parallel indicator) → Research Debate → Trader → Risk Debate → Portfolio Manager
- [ ] Each phase shows: pending (gray), running (blue pulse), done (green check), failed (red X), reused (purple)
- [ ] Use HTML/CSS for the stepper (st.markdown with unsafe_allow_html)

### Task 3: Live log panel layout
- [ ] During active run: use `st.columns([3, 1])` — reports left, log right
- [ ] Log panel: `st.container(height=500)` with scrollable log lines
- [ ] After completion: full-width `render_decision_first()` (no log panel)

### Task 4: Decision-first layout for completed results
- [ ] **NOTE: Core replacement done in Sprint 2 Task 10.** This task covers remaining integration:
- [ ] Verify `render_decision_first()` handles the `from_cache` path correctly (cached data dict format)
- [ ] Ensure the price chart still renders above the decision-first layout
- [ ] Remove any remaining dead code from old `_render_reports()` tabs-based rendering

### Task 5: Inline ticker validation with debounce
- [ ] Add `st.session_state["_last_validation_time"]` timestamp
- [ ] On each rerun where ticker value changed AND 600ms elapsed: call `validate_ticker()`
- [ ] Show result inline below ticker input: `st.success()` or `st.error()`
- [ ] Don't validate during active run or during auto-refresh cycles
- [ ] Cache validation result per ticker value to avoid re-validating on rerun

## History UX

### Task 6: Ticker search filter
- [ ] Add `st.text_input("🔍 Search ticker", key="hist_search")` above summary table
- [ ] Filter records where ticker contains search string (case-insensitive)
- [ ] Pass as `ticker` parameter to `list_analyses()` when using SQLite

### Task 7: Date range filter
- [ ] Add two `st.date_input` widgets: "From" and "To"
- [ ] Default: From = 30 days ago, To = today
- [ ] Pass as `date_from`/`date_to` to `list_analyses()`
- [ ] Filesystem fallback: filter in Python after loading

### Task 8: Return filter (SQLite-dependent)
- [ ] If `is_db_available()`: show `st.slider("Min return %", -50, 100, 0)`
- [ ] Query: JOIN analyses with memory_entries WHERE raw_return >= slider_value
- [ ] If SQLite unavailable: hide the slider entirely (graceful degradation)

### Task 9: Decision-first detail panel
- [ ] Replace current `_render_run_detail()` internals with `render_decision_first(data)`
- [ ] Keep the "Open in Chat" and "Run Again" buttons above the detail
- [ ] Load full data via `load_run(record["file"])` only when expander is opened

### Task 10: Summary table from SQLite
- [ ] Replace `list_history()` call with `list_history_summary()` for the table
- [ ] Table shows: Ticker, Date, Rating (colored pill), Conviction
- [ ] Full data loaded on-demand when user expands a row

## Compare UX

### Task 11: Ticker filter above dropdowns
- [ ] Add `st.text_input("Filter A", key="cmp_filter_a")` above Analysis A selectbox
- [ ] Filter the options list by ticker containing the filter string
- [ ] Same for Analysis B
- [ ] When filter hides current selection: show info message, don't auto-select

### Task 12: Comparison table
- [ ] After both analyses selected: render a 2-column comparison table
- [ ] Rows: Rating, Conviction, Price Target, Time Horizon
- [ ] Verdict row: "A is more bullish" / "B is more bullish" / "Same rating"
- [ ] Use `compute_conviction()` for conviction values
- [ ] Same-ticker-date notice when applicable

### Task 13: "Compare both in Chat" button
- [ ] Add button below comparison table
- [ ] On click: set `st.session_state["chat_multi_prefill"] = [key_a, key_b]`
- [ ] Navigate to Chat view
- [ ] Disable button when A == B (same selection warning)

### Task 14: Replace tabs with expanders in Compare
- [ ] In `_render_side()`: replace `st.tabs()` with individual `st.expander()` per report section
- [ ] Final Decision expander expanded by default, others collapsed
- [ ] Apply `sanitize_report()` to all content
