# Tasks — Sprint 4: Parallel Infrastructure (Worker Pool, Multi-Ticker)

## Worker Pool

### Task 1: Create `dashboard/worker_pool.py`
- [ ] Implement `WorkerPool` class with `__init__(session_id, max_concurrency)`
- [ ] Implement `dispatch()` — spawns thread, adds to `_active` dict, respects concurrency limit
- [ ] Implement `drain_results()` — returns and clears completed results (thread-safe)
- [ ] Implement `cancel(ticker)` — sets cancelled flag on the ticker's RunState
- [ ] Implement `cancel_all()` — cancels all active workers
- [ ] Implement `active_count()`, `active_tickers()`, `update_max_concurrency()`
- [ ] Each worker thread calls `run_analysis()` and appends result to `_results` on completion
- [ ] Test: dispatch 3 tickers with concurrency=2 → only 2 run simultaneously

### Task 2: Add `portfolio_context` to `run_analysis()`
- [ ] Add `portfolio_context: Optional[str] = None` parameter to `run_analysis()` in `runner.py`
- [ ] In `_worker()`: if `portfolio_context` provided, append to `past_context` in initial state
- [ ] Test: pass portfolio_context → verify it appears in final_state's past_context

## Multi-Ticker View Rewrite

### Task 3: Rename navigation
- [ ] In `streamlit_app.py`: change "📋 Watchlist" to "📊 Multi-Ticker Analysis"
- [ ] Keep file as `watchlist.py` (no import changes)

### Task 4: Replace sequential dispatch with WorkerPool
- [ ] Remove old `_dispatch_next()`, `_drain_results_and_advance()`, module-level buffer
- [ ] Initialize `WorkerPool` in session_state on first render
- [ ] Main render loop: `pool.drain_results()` → update results list → dispatch from queue if slots free
- [ ] Test: queue 5 tickers, concurrency=3 → 3 run in parallel, 2 wait

### Task 5: Max Concurrency slider
- [ ] Add `st.slider("Max Concurrent", 1, 5, 3, key="wl_concurrency")` in sidebar
- [ ] On change: call `pool.update_max_concurrency(value)`
- [ ] Disable slider while no batch is running (or keep enabled for live adjustment)

### Task 6: Import from Portfolio button
- [ ] Add "📥 Import from Portfolio" button in sidebar
- [ ] On click: query `list_positions()` from `dashboard/db.py`
- [ ] Populate ticker text area with portfolio tickers
- [ ] If no portfolio positions: show info message

### Task 7: Skip button per active ticker
- [ ] In the "Currently Running" section, show a "⏭ Skip" button per active ticker
- [ ] On click: call `pool.cancel(ticker)` → worker detects cancellation at next checkpoint
- [ ] Show "Skipped" status in results table

### Task 8: Rating distribution chart
- [ ] After results section: render a bar chart of rating counts
- [ ] Use `st.bar_chart()` or plotly: x=rating categories, y=count, colored by rating
- [ ] Only show when ≥2 results exist

### Task 9: "Analyze in Chat" shortcut
- [ ] Per completed result: add "💬 Chat" button
- [ ] On click: `invalidate_history_cache()`, set prefill keys, navigate to Chat
- [ ] Same pattern as existing "Open in Chat" but with cache invalidation (Bug 8 fix)

### Task 10: Fast Mode for batch
- [ ] Add "⚡ Fast Mode" toggle in sidebar (same as Single Ticker)
- [ ] Add "Max days to look back" slider when enabled
- [ ] For each ticker in queue: check `find_recent_run()` before dispatch
- [ ] If prior run found: pass as `prior_run` to `run_analysis()`
- [ ] Show stale fundamentals warning per result
- [ ] Add "🔄 Re-run Full" button next to warned results

### Task 11: Mid-batch ticker addition
- [ ] Keep "Add to Queue" button enabled during batch (remove `disabled=wl_running`)
- [ ] Validate tickers before appending (consistent with initial add)
- [ ] Show updated queue length immediately

### Task 12: Global run guard
- [ ] Add `st.session_state["_global_run_active"]` flag
- [ ] Set True when any view starts a run, False when complete
- [ ] Other views check this flag and disable their Run buttons with message
- [ ] Test: start Multi-Ticker batch → Single Ticker Run button disabled
