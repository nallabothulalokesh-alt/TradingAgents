# Design Document — Sprint 3: UX Improvements

## Overview

Apply the decision-first layout, search/filter capabilities, and improved navigation to the three core views: Single Ticker, History, and Compare. All changes are UI-only — the backend foundation from Sprints 1-2 is consumed here.

## Single Ticker UX

### Changes
1. **Progress bar** — overall percentage based on agents completed/total
2. **Timeline stepper** — visual pipeline stages (Analysts → Research → Trader → Risk → PM) with parallel analyst indicators
3. **Live log panel** — scrollable log beside reports during active run
4. **Decision-first layout** — use `render_decision_first()` for completed results
5. **Ticker validation** — inline validation with debounce (600ms between reruns)
6. **Auto-refresh via fragment** — already done in Sprint 2 Bug 17

### Key Design Decision
The live-progress view (during run) and the completed view (after run/from cache) use DIFFERENT rendering:
- **During run:** Reports appear incrementally as agents complete (current behavior, keep it)
- **After completion:** Switch to `render_decision_first()` for the polished layout

## History UX

### Changes
1. **Ticker search** — `st.text_input` filter above the summary table
2. **Date range filter** — two `st.date_input` widgets (from/to)
3. **Return filter** — slider for minimum raw return (requires memory entries join)
4. **Decision-first detail panel** — replace current tabs with `render_decision_first()` in expander
5. **Summary table via SQLite** — `list_analyses()` with filters passed as SQL WHERE clauses

### Key Design Decision
The return filter JOINs `analyses` with `memory_entries` in SQLite:
```sql
SELECT a.* FROM analyses a
JOIN memory_entries m ON a.ticker = m.ticker AND a.trade_date = m.trade_date
WHERE m.raw_return >= ?
```
When SQLite is unavailable, the return filter is hidden (graceful degradation).

## Compare UX

### Changes
1. **Ticker filter** — text input above each dropdown to narrow options
2. **Comparison table** — side-by-side metrics (Rating, Conviction, Price Target, Time Horizon, Verdict)
3. **"Compare both in Chat"** button — sets `chat_multi_prefill` and navigates
4. **Executive summary** — inline below comparison table
5. **Filter-hides-selection** — don't auto-select when filter removes current selection

### Key Design Decision
Dropdowns use `list_history_summary()` (lightweight) for options. Full data loaded via `load_run()` only when a selection is made. This keeps the Compare view fast even with 1000+ analyses.

## Files Modified

| File | Changes |
|------|---------|
| `dashboard/views/single_ticker.py` | Progress bar, timeline stepper, live log layout, decision-first for completed |
| `dashboard/views/history.py` | Search, date filter, return filter, decision-first detail, SQLite queries |
| `dashboard/views/compare.py` | Ticker filter, comparison table, "Compare in Chat", executive summary |
