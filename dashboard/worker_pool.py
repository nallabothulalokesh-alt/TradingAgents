"""Shared Worker Pool for parallel analysis execution.

Used by Multi-Ticker Analysis and Portfolio batch analysis views.
Each session gets its own WorkerPool instance stored in session_state.
"""

import threading
from typing import Any, Dict, List, Optional

from dashboard.utils import RunState
from dashboard.runner import run_analysis


class WorkerPool:
    """Session-scoped parallel analysis executor."""

    def __init__(self, session_id: str, max_concurrency: int = 3):
        self._session_id = session_id
        self._max_concurrency = max_concurrency
        self._active: Dict[str, _WorkerHandle] = {}  # ticker → handle
        self._results: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    def update_max_concurrency(self, n: int):
        self._max_concurrency = max(1, min(n, 10))

    def dispatch(
        self,
        ticker: str,
        date: str,
        analysts: List[str],
        config: Dict[str, Any],
        portfolio_context: Optional[str] = None,
        prior_run: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Start analysis for ticker if under concurrency limit.

        Returns True if dispatched, False if at capacity.
        """
        with self._lock:
            if len(self._active) >= self._max_concurrency:
                return False
            if ticker in self._active:
                return False  # already running

        rs = RunState()
        handle = _WorkerHandle(ticker, date, rs)

        def _worker():
            # THREAD SAFETY: Do NOT access st.session_state here.
            t = run_analysis(rs, ticker, date, analysts, config,
                            prior_run=prior_run)
            # Wait for the inner thread to complete (no polling)
            if t is not None:
                t.join()
            snap = rs.snapshot()
            result = {
                "ticker": snap["ticker"],
                "date": snap["trade_date"],
                "decision": snap["decision"] or "—",
                "rating": snap["decision"] or "—",
                "error": snap["error"],
                "final_state": snap["final_state"],
                "portfolio_context": portfolio_context,
            }
            with self._lock:
                self._results.append(result)
                self._active.pop(ticker, None)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        handle.thread = t

        with self._lock:
            self._active[ticker] = handle
        return True

    def drain_results(self) -> List[Dict[str, Any]]:
        """Return and clear completed results. Called from main thread only."""
        with self._lock:
            results = list(self._results)
            self._results.clear()
        return results

    def cancel(self, ticker: str):
        """Cancel a specific active worker."""
        with self._lock:
            handle = self._active.get(ticker)
        if handle:
            handle.run_state.request_cancel()

    def cancel_all(self):
        """Cancel all active workers."""
        with self._lock:
            handles = list(self._active.values())
        for handle in handles:
            handle.run_state.request_cancel()

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def active_tickers(self) -> Dict[str, RunState]:
        """Return {ticker: RunState} for all active workers."""
        with self._lock:
            return {t: h.run_state for t, h in self._active.items()}

    def is_idle(self) -> bool:
        with self._lock:
            return len(self._active) == 0 and len(self._results) == 0


class _WorkerHandle:
    """Internal handle for a running worker."""

    def __init__(self, ticker: str, date: str, run_state: RunState):
        self.ticker = ticker
        self.date = date
        self.run_state = run_state
        self.thread: Optional[threading.Thread] = None
