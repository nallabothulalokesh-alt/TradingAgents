"""Shared helpers for the TradingAgents dashboard."""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG

# ── Paths ─────────────────────────────────────────────────────────────────────
RESULTS_DIR = Path(DEFAULT_CONFIG["results_dir"])
MEMORY_LOG  = Path(DEFAULT_CONFIG["memory_log_path"])

# ── Rating helpers ─────────────────────────────────────────────────────────────
RATING_ORDER = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]

RATING_COLORS = {
    "Buy":         "#16a34a",
    "Overweight":  "#4ade80",
    "Hold":        "#ca8a04",
    "Underweight": "#f97316",
    "Sell":        "#dc2626",
}

RATING_BADGE = {
    r: f'<span class="badge-{r.lower()}">{r}</span>' for r in RATING_ORDER
}


def rating_badge(rating: str) -> str:
    return RATING_BADGE.get(rating, f"<span>{rating}</span>")


# ── Ticker validation ─────────────────────────────────────────────────────────

# Common mistakes: company full name → correct ticker symbol.
# Keys must be words people type INSTEAD of the real ticker.
# Never add an entry where the key is already the correct ticker.
_COMMON_NAMES = {
    "APPLE":      "AAPL",
    "MICROSOFT":  "MSFT",
    "GOOGLE":     "GOOGL",
    "ALPHABET":   "GOOGL",
    "AMAZON":     "AMZN",
    "TESLA":      "TSLA",
    "FACEBOOK":   "META",
    "NETFLIX":    "NFLX",
    "NVIDIA":     "NVDA",
    "INTEL":      "INTC",
    "SAMSUNG":    "005930.KS",
    "TOYOTA":     "7203.T",
    "TENCENT":    "0700.HK",
    "ALIBABA":    "BABA",
    "BERKSHIRE":  "BRK-B",
    "JPMORGAN":   "JPM",
    "GOLDMAN":    "GS",
    "MASTERCARD": "MA",
    "PALANTIR":   "PLTR",
    "COINBASE":   "COIN",
    "SNOWFLAKE":  "SNOW",
    "AIRBNB":     "ABNB",
    "SPOTIFY":    "SPOT",
    "SHOPIFY":    "SHOP",
}


def validate_ticker(ticker: str) -> tuple[bool, str]:
    """Check whether a ticker exists and has tradeable price data on yfinance.

    Returns (is_valid, message).
    Fast — only fetches 10 days of history, no fundamentals call.
    """
    if not ticker or not ticker.strip():
        return False, "Ticker cannot be empty."

    ticker = ticker.strip().upper()

    # Check if user typed a company name instead of a ticker
    if ticker in _COMMON_NAMES:
        suggestion = _COMMON_NAMES[ticker]
        return False, (
            f"'{ticker}' is a company name, not a ticker symbol. "
            f"Did you mean **{suggestion}**?"
        )

    # Basic format check — letters, digits, dots, hyphens only
    import re
    if not re.match(r'^[A-Z0-9.\-]{1,20}$', ticker):
        return False, f"'{ticker}' doesn't look like a valid ticker symbol."

    try:
        import yfinance as yf
        from datetime import date, timedelta
        end   = date.today()
        start = end - timedelta(days=10)
        hist  = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
        )
        if hist.empty:
            return False, (
                f"'{ticker}' returned no price data. "
                "Double-check the symbol — non-US stocks need an exchange suffix "
                "(e.g. 7203.T for Toyota, 0700.HK for Tencent)."
            )
        return True, f"✅ {ticker} — valid ({len(hist)} trading days found)"
    except Exception as e:
        err = str(e)
        if "ISIN" in err or "No data" in err.lower():
            return False, (
                f"'{ticker}' not found. Check the symbol is correct "
                "(non-US stocks need an exchange suffix, e.g. 7203.T, 0700.HK)."
            )
        return False, f"Could not verify '{ticker}': {err}"


# ── Default config for the dashboard ─────────────────────────────────────────
DASHBOARD_CONFIG = {
    **DEFAULT_CONFIG,
    "llm_provider":    "deepseek",
    "deep_think_llm":  "deepseek-v4-pro",
    "quick_think_llm": "deepseek-v4-flash",
    "max_debate_rounds":       1,
    "max_risk_discuss_rounds": 1,
    "data_vendors": {
        "core_stock_apis":      "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data":     "yfinance",
        "news_data":            "yfinance",
    },
}

ALL_ANALYSTS = ["market", "social", "news", "fundamentals"]

# ── Agent pipeline order (for progress display) ───────────────────────────────
AGENT_TEAMS = {
    "Analyst Team":       ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"],
    "Research Team":      ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team":       ["Trader"],
    "Risk Management":    ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"],
    "Portfolio Mgmt":     ["Portfolio Manager"],
}

ANALYST_TO_AGENT = {
    "market":       "Market Analyst",
    "social":       "Social Analyst",
    "news":         "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

# ── History helpers ───────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def list_history() -> List[Dict[str, Any]]:
    """Return all saved analysis runs, newest first.

    Cached for 30 s so repeated renders don't re-scan the filesystem.
    The cache is invalidated automatically after TTL or when
    invalidate_history_cache() is called (e.g. after a new run completes).
    """
    records = []
    if not RESULTS_DIR.exists():
        return records

    for ticker_dir in sorted(RESULTS_DIR.iterdir()):
        if not ticker_dir.is_dir():
            continue
        log_dir = ticker_dir / "TradingAgentsStrategy_logs"
        if not log_dir.exists():
            continue
        for json_file in sorted(log_dir.glob("full_states_log_*.json"), reverse=True):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                records.append({
                    "ticker":    data.get("company_of_interest", ticker_dir.name),
                    "date":      data.get("trade_date", ""),
                    "decision":  data.get("final_trade_decision", ""),
                    "rating":    _extract_rating(data.get("final_trade_decision", "")),
                    "file":      json_file,
                    "data":      data,
                })
            except Exception:
                pass
    return records


def invalidate_history_cache() -> None:
    """Clear the list_history cache so the next render picks up new runs."""
    list_history.clear()


def load_run(json_file: Path) -> Dict[str, Any]:
    return json.loads(json_file.read_text(encoding="utf-8"))


# ── Chat history persistence ──────────────────────────────────────────────────

def _chat_history_path(analysis_file: Path) -> Path:
    """Return the chat history JSON path that sits next to the analysis file."""
    return analysis_file.parent / analysis_file.name.replace(
        "full_states_log_", "chat_history_"
    )


@st.cache_data(ttl=60, show_spinner=False)
def _cached_chat_msg_count(analysis_file_str: str) -> int:
    """Return the number of saved chat messages for a given analysis file path.

    Cached so the chat dropdown doesn't do N disk reads on every render.
    Pass the path as a string because Path objects aren't hashable by st.cache_data.
    """
    path = Path(analysis_file_str).parent / Path(analysis_file_str).name.replace(
        "full_states_log_", "chat_history_"
    )
    if not path.exists():
        return 0
    try:
        return len(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return 0


def load_chat_history(analysis_file: Path) -> List[Dict[str, str]]:
    """Load persisted chat history for a given analysis file. Returns [] if none."""
    path = _chat_history_path(analysis_file)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_chat_history(analysis_file: Path, history: List[Dict[str, str]]) -> None:
    """Persist chat history to disk next to the analysis file."""
    path = _chat_history_path(analysis_file)
    try:
        path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        # Bust the badge-count cache so the dropdown reflects the new count
        _cached_chat_msg_count.clear()
    except Exception:
        pass  # never crash the UI over a save failure


def sanitize_report(text: str) -> str:
    """Remove artefacts that should never appear in a rendered report."""
    import re as _re

    if not text:
        return text

    cleaned = _re.sub(r'<tool_calls>.*?</tool_calls>', '', text, flags=_re.DOTALL)
    cleaned = _re.sub(r'<[^>]+>.*?</[^>]+>', '', cleaned, flags=_re.DOTALL)
    cleaned = _re.sub(r'<tool_calls>.*?</tool_calls>', '', cleaned, flags=_re.DOTALL)
    cleaned = _re.sub(r'</?(?:antml:)?tool_call[^>]*>', '', cleaned)
    cleaned = _re.sub(r'</?(?:antml:)?parameter[^>]*>', '', cleaned)
    cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    if not cleaned:
        return (
            "⚠️ **Report generation failed** — the model returned tool-call markup "
            "instead of analysis text. This is caused by `deepseek-reasoner`. "
            "Switch the **Deep thinker** to `deepseek-v4-pro` or `deepseek-chat` and re-run."
        )
    return cleaned


def find_cached_run(ticker: str, trade_date: str) -> Optional[Dict[str, Any]]:
    """Return the saved run data if ticker+date already exists in logs, else None."""
    safe = ticker.strip().upper()
    log_file = RESULTS_DIR / safe / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"
    if log_file.exists():
        try:
            return json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            return None
    for record in list_history():
        if record["ticker"].upper() == safe and record["date"] == trade_date:
            return record["data"]
    return None


def cached_dates_for_ticker(ticker: str) -> List[str]:
    """Return list of dates (YYYY-MM-DD) that have saved results for this ticker."""
    dates = []
    for record in list_history():
        if record["ticker"].upper() == ticker.strip().upper():
            dates.append(record["date"])
    return sorted(dates, reverse=True)


def find_recent_run(ticker: str, before_date: str, max_days: int = 7) -> Optional[Dict[str, Any]]:
    """Return the most recent saved run for ticker within max_days before before_date."""
    from datetime import datetime as _dt
    try:
        target = _dt.strptime(before_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    best: Optional[Dict[str, Any]] = None
    best_date = None

    for record in list_history():
        if record["ticker"].upper() != ticker.strip().upper():
            continue
        if record["date"] == before_date:
            continue
        try:
            rec_date = _dt.strptime(record["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        days_diff = (target - rec_date).days
        if 0 < days_diff <= max_days:
            if best_date is None or rec_date > best_date:
                best = record["data"]
                best_date = rec_date

    if best is not None:
        best["_prior_date"] = str(best_date)
    return best


def fast_mode_summary(prior_run: Dict[str, Any], target_date: str) -> str:
    """Human-readable summary of what will be reused from the prior run."""
    from datetime import datetime as _dt
    prior_date = prior_run.get("_prior_date", prior_run.get("trade_date", "?"))
    try:
        days = (_dt.strptime(target_date, "%Y-%m-%d").date()
                - _dt.strptime(prior_date, "%Y-%m-%d").date()).days
    except Exception:
        days = "?"
    reused = []
    if prior_run.get("fundamentals_report"):
        reused.append("Fundamentals")
    if prior_run.get("investment_plan"):
        reused.append("Research Plan")
    skipped = " + ".join(reused) if reused else "nothing"
    return f"Prior run: {prior_date} ({days}d ago) — reusing: {skipped}"


def check_stale_fundamentals(ticker: str, prior_date: str, target_date: str) -> Optional[str]:
    """Check if earnings occurred between prior_date and target_date.

    Returns a warning string if fundamentals may be stale, None otherwise.
    Wraps the inner earnings loop in its own try/except so a yfinance API
    failure never blocks the UI.
    """
    try:
        import yfinance as yf
        from datetime import datetime as _dt

        prior_dt  = _dt.strptime(prior_date,  "%Y-%m-%d").date()
        target_dt = _dt.strptime(target_date, "%Y-%m-%d").date()

        stock = yf.Ticker(ticker)
        try:
            earnings_dates = stock.earnings_dates
            if earnings_dates is not None and not earnings_dates.empty:
                for idx in earnings_dates.index:
                    earnings_date = idx.date() if hasattr(idx, "date") else idx
                    if prior_dt < earnings_date <= target_dt:
                        return (
                            f"⚠️ Earnings released on {earnings_date} — "
                            "fundamentals from prior run may be outdated"
                        )
        except Exception:
            pass  # earnings_dates API can fail silently

        return None
    except Exception:
        return None


def _extract_rating(text: str) -> str:
    from tradingagents.agents.utils.rating import parse_rating
    return parse_rating(text)


# ── Memory log helpers ────────────────────────────────────────────────────────

def load_memory_entries() -> List[Dict[str, Any]]:
    """Parse the markdown memory log into a list of dicts."""
    if not MEMORY_LOG.exists():
        return []
    from tradingagents.agents.utils.memory import TradingMemoryLog
    log = TradingMemoryLog({"memory_log_path": str(MEMORY_LOG)})
    return log.load_entries()


# ── Live-run state (shared across threads) ────────────────────────────────────

class RunState:
    """Thread-safe container for a single live analysis run."""

    def __init__(self):
        self._lock      = threading.Lock()
        self._cancelled = threading.Event()   # set → background thread should abort
        self.reset()

    def reset(self):
        with self._lock:
            self.running      = False
            self.done         = False
            self.error        = None
            self.ticker       = ""
            self.trade_date   = ""
            self.agent_status: Dict[str, str] = {}
            self.reports: Dict[str, str]       = {}
            self.log_lines: List[str]          = []
            self.warnings: List[str]           = []
            self.final_state  = None
            self.decision     = None
        self._cancelled.clear()

    # ── Cancellation ─────────────────────────────────────────────────────────

    def request_cancel(self):
        """Signal the background thread to stop at the next checkpoint."""
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    # ── Setters (called from background thread) ───────────────────────────────

    def set_agent(self, agent: str, status: str):
        with self._lock:
            self.agent_status[agent] = status

    def set_report(self, section: str, content: str):
        with self._lock:
            self.reports[section] = content

    def append_log(self, line: str):
        with self._lock:
            self.log_lines.append(line)
            if len(self.log_lines) > 300:
                self.log_lines = self.log_lines[-300:]

    def add_warning(self, warning: str):
        with self._lock:
            if warning not in self.warnings:
                self.warnings.append(warning)

    def finish(self, final_state, decision):
        with self._lock:
            self.final_state = final_state
            self.decision    = decision
            self.running     = False
            self.done        = True

    def fail(self, exc: Exception):
        with self._lock:
            self.error   = str(exc)
            self.running = False
            self.done    = True

    # ── Getters (called from Streamlit main thread) ───────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running":      self.running,
                "done":         self.done,
                "error":        self.error,
                "ticker":       self.ticker,
                "trade_date":   self.trade_date,
                "agent_status": dict(self.agent_status),
                "reports":      dict(self.reports),
                "log_lines":    list(self.log_lines),
                "warnings":     list(self.warnings),
                "final_state":  self.final_state,
                "decision":     self.decision,
            }
