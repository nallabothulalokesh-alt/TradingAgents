# Design Document — Sprint 2: Shared Utilities + Quick Fixes

## Overview

Extract shared utilities that multiple views depend on, and fix the remaining medium-priority bugs. After this sprint, all foundation work is complete and UX sprints can begin.

## Part 1: Shared Utilities

### `compute_conviction(reports: dict) -> tuple[str, str]`

Extract from `single_ticker.py` `_conviction()` to `dashboard/utils.py`. No logic change — just move and make public.

### `render_decision_first(data: dict, container) -> None`

New function in `dashboard/utils.py` that encapsulates the decision-first rendering pattern currently duplicated across views. It:
1. Extracts rating from `final_trade_decision` via `_extract_rating()`
2. Renders decision banner (colored div)
3. Extracts Price Target, Time Horizon, Executive Summary via case-insensitive regex
4. HTML-escapes extracted values (Bug 16 fix built-in)
5. Renders Key Metrics Row (Price Target, Time Horizon, Conviction)
6. Renders Executive Summary inline
7. Renders analyst report expanders (collapsed)
8. Renders pipeline expanders (Research Plan, Trader Plan, Final Decision)
9. Applies `sanitize_report()` to all text
10. Uses trader plan key fallback (Bug 5 built-in)

The `container` parameter is a Streamlit container (st, column, expander) to render into.

### `list_history_summary()` → Thin wrapper (resolves spec contradiction)

**Clarification:** Three specs reference this function differently. The definitive design:
- `list_history_summary()` EXISTS as a public function in `dashboard/utils.py`
- When SQLite is available: it delegates to `list_analyses()` from `dashboard/db.py`
- When SQLite is unavailable: it scans the filesystem and returns lightweight dicts (ticker, date, rating, file path, portfolio_context — NO full report text)
- It does NOT return `final_trade_decision` text (that's heavy) — it returns the pre-extracted `rating` string
- The SQLite spec's "replaced by" language means the IMPLEMENTATION is replaced (by SQLite query), not that the function is deleted
- All consumers call `list_history_summary()` — they never call `list_analyses()` directly (abstraction layer)

## Part 2: Remaining Bug Fixes

### Bug 7: Chat prefill fallback
Change `0` to `None` in the `next(...)` call in `chat.py`. Show info message when not found.

### Bug 8: Per-result cache invalidation
Add `invalidate_history_cache()` call in watchlist.py "Open in Chat" button handler, BEFORE setting nav target.

### Bug 9: Context window overflow
In `chat.py` `_stream_llm()`:
- Estimate tokens: `sum(len(m["content"].split()) for m in messages) * 1.3`
- Define model limits dict
- If over 80%: trim oldest messages (keep system + most recent)
- If system prompt alone > 80%: truncate system prompt, show warning

### Bug 10: "Run Again" date prefill
In history.py "Run Again" handler: set `st.session_state["st_prefill_date"]`.
In single_ticker.py: read and consume it for date_input default.

### Bug 13: Per-ticker date validation warning
In watchlist.py "Add to Queue" handler: show `st.warning()` when date parse fails.

### Bug 17: time.sleep replacement
Check Streamlit version at import time. If ≥1.33: use `@st.fragment(run_every=...)`. If not: keep `time.sleep` with comment.

Structure: extract the auto-refresh section into a fragment function in both `single_ticker.py` and `watchlist.py`.

## Files Modified

| File | Changes |
|------|---------|
| `dashboard/utils.py` | Add `compute_conviction()`, `render_decision_first()`, `list_history_summary()` |
| `dashboard/views/single_ticker.py` | Remove `_conviction()`, replace `_render_reports()` with `render_decision_first()`, extract fragment for auto-refresh |
| `dashboard/views/chat.py` | Bug 7 (prefill fallback), Bug 9 (token overflow) |
| `dashboard/views/watchlist.py` | Bug 8 (cache invalidation), Bug 13 (date warning), Bug 17 (fragment) |
| `dashboard/views/history.py` | Bug 10 (date prefill) |
