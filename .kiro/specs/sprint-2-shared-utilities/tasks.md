# Tasks — Sprint 2: Shared Utilities + Quick Fixes

## Shared Utilities

### Task 1: Extract `compute_conviction()` to utils.py
- [ ] Copy `_conviction()` from `single_ticker.py` to `dashboard/utils.py` as `compute_conviction(reports: dict) -> tuple[str, str]`
- [ ] In `single_ticker.py`, replace `_conviction(reports)` calls with `compute_conviction(reports)` import
- [ ] Remove the private `_conviction()` function from `single_ticker.py`
- [ ] Test: `compute_conviction({"market_report": "x", ...})` returns correct level

### Task 2: Build `render_decision_first()` utility
- [ ] In `dashboard/utils.py`, create `render_decision_first(data: dict, container=None) -> None`
- [ ] If `container` is None, use `st` directly
- [ ] Extract rating via `_extract_rating(data.get("final_trade_decision", ""))`
- [ ] Render decision banner with colored div
- [ ] Extract Price Target, Time Horizon, Executive Summary with case-insensitive regex: `(?i)\*\*Price\s+Target\*\*[:\s]*([^\n]+)`
- [ ] HTML-escape all extracted values
- [ ] Render Key Metrics Row (Price Target, Time Horizon, Conviction via `compute_conviction()`)
- [ ] Render Executive Summary inline (no expander)
- [ ] Render analyst reports as collapsed expanders (market, news, fundamentals, sentiment)
- [ ] Render pipeline expanders (Research Plan, Trader Plan with fallback, Final Decision expanded)
- [ ] Apply `sanitize_report()` to all report text
- [ ] Skip any section that's empty/missing (graceful degradation)
- [ ] Test: call with empty dict → no crash. Call with full data → all sections render.

### Task 3: Implement `list_history_summary()`
- [ ] In `dashboard/utils.py`, add `list_history_summary() -> List[Dict]`
- [ ] If `is_db_available()`: return `list_analyses()` from `dashboard/db.py`
- [ ] Else: scan filesystem, parse each JSON, return only lightweight fields (ticker, date, rating, file, portfolio_context)
- [ ] Cache with `@st.cache_data(ttl=30)` for the filesystem fallback path only
- [ ] Test: verify returns same records as `list_history()` but without `data` key

## Bug Fixes

### Task 4: Chat prefill fallback (Bug 7)
- [ ] In `dashboard/views/chat.py`, change the `index=next(...)` default from `0` to `None`
- [ ] When index is None: show `st.info("Analysis for {ticker} on {date} not found...")` and don't auto-select
- [ ] Handle `None` index in `st.selectbox` (use `index=0` only when prefill not attempted)
- [ ] Clear prefill keys after consumption (already done)
- [ ] Test: set prefill for non-existent analysis → info message shown, no crash

### Task 5: Per-result cache invalidation (Bug 8)
- [ ] In `dashboard/views/watchlist.py`, in the "💬 Open in Chat" button handler:
  - Add `invalidate_history_cache()` BEFORE setting `_nav_target`
- [ ] Import `invalidate_history_cache` from `dashboard.utils`
- [ ] Test: complete one result in batch, click "Open in Chat" → chat finds the analysis

### Task 6: Context window overflow (Bug 9)
- [ ] In `dashboard/views/chat.py`, add `_MODEL_CONTEXT_LIMITS` dict at module level
- [ ] In `_stream_llm()`, before building `lc_msgs`:
  - Estimate total tokens: `(len(system_prompt.split()) + sum(len(m["content"].split()) for m in messages)) * 1.3`
  - Get limit from `_MODEL_CONTEXT_LIMITS.get(model, 8000)`
  - If total > 80% of limit: trim oldest messages (keep system + last N that fit)
  - If system prompt alone > 80%: truncate system prompt, add warning to return
- [ ] Show notice in UI when trimming occurs
- [ ] Test: send 100 long messages → no API error, trimming notice shown

### Task 7: "Run Again" date prefill (Bug 10)
- [ ] In `dashboard/views/history.py` "Run Again" button handler: add `st.session_state["st_prefill_date"] = record["date"]`
- [ ] In `dashboard/views/single_ticker.py`: read `st.session_state.pop("st_prefill_date", None)` and use as date_input default
- [ ] Test: click "Run Again" on a historical analysis → Single Ticker shows that date

### Task 8: Per-ticker date validation warning (Bug 13)
- [ ] In `dashboard/views/watchlist.py` "Add to Queue" handler, in the date parse `except ValueError`:
  - Add `st.warning(f"{ticker}: date '{parts[1]}' is not valid (use YYYY-MM-DD) — using global date")`
- [ ] Test: enter `NVDA 2026-13-45` → warning shown, ticker still queued with global date

### Task 9: time.sleep replacement (Bug 17)
- [ ] At top of `dashboard/views/single_ticker.py`, add version check:
  ```python
  import streamlit as st
  _ST_VERSION = tuple(int(x) for x in st.__version__.split('.')[:2])
  _HAS_FRAGMENT = _ST_VERSION >= (1, 33)
  ```
- [ ] If `_HAS_FRAGMENT`: extract the auto-refresh section into a `@st.fragment(run_every=timedelta(seconds=2))` decorated function
- [ ] If not `_HAS_FRAGMENT`: try `from streamlit_autorefresh import st_autorefresh` — if available, use `st_autorefresh(interval=2000)`
- [ ] If neither available: keep existing `time.sleep(2); st.rerun()` pattern with code comment: "# FALLBACK: blocking sleep — upgrade Streamlit to 1.33+ for non-blocking refresh"
- [ ] Do the same for `watchlist.py` (3-second interval)
- [ ] Test: verify page auto-refreshes during active run without blocking

## Integration

### Task 10: Update single_ticker.py to use shared utilities
- [ ] Replace `_render_reports()` call for completed/cached results with `render_decision_first(data)`
- [ ] Keep `_render_reports()` for the live-progress partial view (reports appearing incrementally)
- [ ] Verify all existing functionality preserved
- [ ] Remove this task from Sprint 3 (Sprint 3 Task 4 is now a no-op — mark as "done in Sprint 2")
