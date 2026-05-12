# Design Document — Sprint 4: Parallel Infrastructure (Worker Pool, Multi-Ticker)

## Overview

Extract the parallel execution infrastructure into a shared module and rebuild the Multi-Ticker Analysis view with concurrent execution, new features, and the renamed navigation.

## Worker Pool Architecture

### Module: `dashboard/worker_pool.py`

```python
class WorkerPool:
    """Session-scoped parallel analysis executor."""

    def __init__(self, session_id: str, max_concurrency: int = 3):
        self._session_id = session_id
        self._max_concurrency = max_concurrency
        self._active: Dict[str, threading.Thread] = {}  # ticker → thread
        self._results: List[Dict] = []
        self._lock = threading.Lock()

    def dispatch(self, ticker, date, analysts, config, portfolio_context=None, prior_run=None):
        """Start analysis for ticker if under concurrency limit. Returns True if dispatched."""

    def drain_results(self) -> List[Dict]:
        """Return and clear completed results. Called from main thread."""

    def cancel(self, ticker: str): ...
    def cancel_all(self): ...
    def active_count(self) -> int: ...
    def active_tickers(self) -> List[str]: ...
    def update_max_concurrency(self, n: int): ...
```

### Key Design Decisions

1. **One WorkerPool per session** — stored in `st.session_state["_worker_pool"]`
2. **Main thread drives dispatch** — on each render cycle: drain results, check if slots free, dispatch next from queue
3. **Workers only write to pool's results list** — never touch session_state
4. **Concurrency slider** — changes `_max_concurrency` live; main thread respects it on next dispatch cycle

### Multi-Ticker View Changes

1. Rename nav label: "📋 Watchlist" → "📊 Multi-Ticker Analysis" (in `streamlit_app.py`)
2. Replace sequential `_dispatch_next()` with `WorkerPool` usage
3. Add Max Concurrency slider (1-5, default 3)
4. Add "Import from Portfolio" button (reads portfolio positions from SQLite)
5. Add Skip button per active ticker
6. Add rating distribution chart (bar chart of Buy/Hold/Sell counts)
7. Add "Analyze in Chat" shortcut per completed result
8. Add Fast Mode toggle for batch (with stale fundamentals warning + "Re-run Full" button)

### `run_analysis()` Portfolio Context Parameter

Add optional `portfolio_context: str = None` to `run_analysis()`. When provided, inject into the initial state's `past_context` field so the Portfolio Manager knows the user's position.

## Files Modified/Created

| File | Changes |
|------|---------|
| `dashboard/worker_pool.py` | NEW — shared WorkerPool class |
| `dashboard/views/watchlist.py` | Major rewrite: use WorkerPool, add all new features |
| `streamlit_app.py` | Rename nav label |
| `dashboard/runner.py` | Add `portfolio_context` parameter |
