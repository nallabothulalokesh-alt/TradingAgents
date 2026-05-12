# TradingAgents Dashboard — Session Context

## Project Location
- **Path (WSL):** `/mnt/d/TradingAgents-main`
- **Path (Windows):** `D:\TradingAgents-main`
- **Python venv:** `~/tradingagents-venv` (on Linux filesystem, NOT the Windows mount)
- **Python version:** 3.12.3
- **Activate:** `source ~/tradingagents-venv/bin/activate`
- **Run tests:** `~/tradingagents-venv/bin/python -m pytest tests/ --ignore=tests/test_ticker_symbol_handling.py --tb=short -q`

## Project Overview
A multi-agent LLM trading analysis framework with a Streamlit dashboard. Uses LangGraph for agent orchestration, yfinance for market data, and supports multiple LLM providers (OpenAI, DeepSeek, Anthropic, Google, xAI, Ollama).

### Architecture
```
streamlit_app.py          — Entry point, navigation, CSS
dashboard/
  app.py                  — Thin re-export (exec's streamlit_app.py)
  utils.py                — RunState, list_history(), validate_ticker(), sanitize_report(), etc.
  runner.py               — run_analysis(), _build_fast_graph(), _update_from_state()
  views/
    single_ticker.py      — Single ticker deep dive (run + results)
    watchlist.py          — Multi-ticker batch analysis (sequential queue)
    history.py            — Browse past analyses + memory log
    compare.py            — Side-by-side comparison of two analyses
    chat.py               — LLM chat about a saved analysis
tradingagents/
  default_config.py       — DEFAULT_CONFIG dict
  graph/
    trading_graph.py      — TradingAgentsGraph main class
    setup.py              — GraphSetup (builds LangGraph StateGraph)
    propagation.py        — Propagator (creates initial state)
    conditional_logic.py  — ConditionalLogic (routing decisions)
    signal_processing.py  — SignalProcessor
    reflection.py         — Reflector
    checkpointer.py       — Checkpoint/resume support
  agents/
    analysts/             — Market, News, Social, Fundamentals analysts
    researchers/          — Bull/Bear researchers
    managers/             — Research Manager, Portfolio Manager
    trader/               — Trader agent
    risk_mgmt/            — Aggressive, Conservative, Neutral debators
    utils/
      memory.py           — TradingMemoryLog (markdown append-only log)
      agent_states.py     — AgentState, InvestDebateState, RiskDebateState
      structured.py       — Structured output helpers
      rating.py           — parse_rating()
  dataflows/              — Data fetching (yfinance, alpha vantage)
  llm_clients/            — LLM provider clients (OpenAI, Anthropic, Google, etc.)
```

## Specs (Requirements Documents)
Located in `.kiro/specs/`:
1. **bug-fixes/** — 17 bugs to fix (created this session)
2. **multi-ticker-analysis/** — Rename watchlist, parallel worker pool, decision-first layout, etc.
3. **portfolio-management/** — New Portfolio view with positions, batch analysis, ownership context
4. **single-ticker-ux-improvements/** — Progress bar, timeline stepper, live log, tabs→expanders
5. **history-ux-improvements/** — Decision-first layout, ticker search, date range, return filter
6. **compare-ux-improvements/** — Expanders, ticker filter, comparison table, chat button
7. **analysis-chat-improvements/** — Multi-analysis chat mode, context management
8. **memory-log-json-migration/** — JSON as authoritative store, markdown retained for readability

## Current Bug Fix Progress (2 of 17 done)

### ✅ Completed
1. **Bug 1 (CRITICAL):** Fixed Fast Mode graph — rewrote `_build_fast_graph()` in `runner.py` to build custom StateGraph manually, skipping Bull/Bear/Research Manager nodes entirely.
2. **Bug 2 (CRITICAL):** Fixed watchlist threading — removed `_on_done()` calling `_start_next()` from background thread. New pattern: background thread only writes to `_results_buffer`, main thread drains and advances queue via `_drain_results_and_advance()`.

### 🔲 Remaining (in priority order)
3. **Bug 3 (HIGH):** `_results_buffer` cross-session leakage — scope per session with session-keyed dict
4. **Bug 4 (HIGH):** RunState lock — add `start()` method, remove redundant assignments in `_worker()`
5. **Bug 9 (HIGH):** Chat context window overflow — add truncation to `_stream_llm()`
6. **Bug 5 (MEDIUM):** Trader plan key fallback — use `get("trader_investment_decision") or get("trader_investment_plan")` in history, compare, watchlist
7. **Bug 6 (MEDIUM):** History duplicates — deduplicate by ticker+date in `list_history()`
8. **Bug 7 (MEDIUM):** Chat prefill wrong selection — show message when target not found
9. **Bug 8 (MEDIUM):** "Open in Chat" cache invalidation — call `invalidate_history_cache()` before nav
10. **Bug 13 (MEDIUM):** Per-ticker date validation — show `st.warning()` instead of silent fallback
11. **Bug 14 (MEDIUM):** `list_history_summary()` — lightweight loading for large result sets
12. **Bug 15 (MEDIUM):** `sanitize_report()` — only remove tool_calls/antml tags, not generic HTML
13. **Bug 16 (MEDIUM):** HTML-escape LLM-extracted values before rendering
14. **Bug 17 (MEDIUM):** Replace `time.sleep()` auto-refresh with non-blocking alternative
15. **Bug 10 (LOW):** "Run Again" prefill date — set `st_prefill_date` in history
16. **Bug 11 (LOW):** `safe_ticker_component` — reject whitespace before normalization
17. **Bug 12 (LOW):** Delete `tests/test_ticker_symbol_handling.py`

## Test Status
- **105 passed**, 1 failed (`test_safe_ticker_component::test_rejects_null_byte_and_whitespace` — Bug 11)
- 1 collection error (`test_ticker_symbol_handling.py` — Bug 12)
- Run with: `~/tradingagents-venv/bin/python -m pytest tests/ --ignore=tests/test_ticker_symbol_handling.py --tb=short -q`

## Key Findings from User Journey Analysis (100 scenarios)

### Critical Issues Fixed
- Fast Mode graph was running full pipeline (research team overwrote pre-seeded data)
- Background thread accessed `st.session_state` causing crashes/corruption

### High Issues Remaining
- Module-level buffer shared across Streamlit sessions
- RunState attributes set without lock (race condition)
- Chat sends unbounded history to LLM (context overflow)

### Medium Issues Remaining
- Trader plan key fallback missing in 3 views
- History duplicates for same ticker+date
- Chat silently loads wrong analysis on prefill miss
- Various UX gaps (date prefill, validation warnings, HTML escaping)

## Modified Files This Session
- `/mnt/d/TradingAgents-main/dashboard/runner.py` — Rewrote `_build_fast_graph()`
- `/mnt/d/TradingAgents-main/dashboard/views/watchlist.py` — Rewrote threading model
- `/mnt/d/TradingAgents-main/.kiro/specs/bug-fixes/requirements.md` — Created (17 bugs)
- `/mnt/d/TradingAgents-main/.kiro/specs/multi-ticker-analysis/requirements.md` — Updated
- `/mnt/d/TradingAgents-main/.kiro/specs/portfolio-management/requirements.md` — Updated
- `/mnt/d/TradingAgents-main/.kiro/specs/single-ticker-ux-improvements/requirements.md` — Updated
- `/mnt/d/TradingAgents-main/.kiro/specs/history-ux-improvements/requirements.md` — Updated
- `/mnt/d/TradingAgents-main/.kiro/specs/compare-ux-improvements/requirements.md` — Updated
- `/mnt/d/TradingAgents-main/.kiro/specs/analysis-chat-improvements/requirements.md` — Updated
- `/mnt/d/TradingAgents-main/.kiro/specs/memory-log-json-migration/requirements.md` — Updated

## Next Steps
Continue fixing bugs 3-17 in priority order. After all bugs are fixed, implement new features starting with:
1. Memory Log JSON Migration (isolated, no UI)
2. Shared utilities (compute_conviction → utils.py)
3. Single Ticker UX (progress bar, log panel, tabs→expanders)
4. History UX (decision-first, filters)
5. Compare UX (expanders, search, summary table)
6. Multi-Ticker Analysis (rename, parallel pool, decision layout)
7. Analysis Chat Multi-Mode
8. Portfolio Management (new view)
