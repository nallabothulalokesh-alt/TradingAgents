# Resume Instructions

When starting a new session, paste this to the AI:

---

I'm working on the TradingAgents project at `/mnt/d/TradingAgents-main` (WSL, Windows drive D:).

Please read `.kiro/session-context.md` for full context. The venv is at `~/tradingagents-venv`.

We're fixing 17 bugs documented in `.kiro/specs/bug-fixes/requirements.md`. Bugs 1-2 (CRITICAL) are done. Continue with Bug 3 (HIGH): Fix module-level `_results_buffer` cross-session leakage in `dashboard/views/watchlist.py`.

The task list is:
- ✅ Bug 1: Fast Mode graph fixed (runner.py)
- ✅ Bug 2: Watchlist threading fixed (watchlist.py)
- 🔲 Bug 3: _results_buffer cross-session leakage
- 🔲 Bug 4: RunState lock
- 🔲 Bug 9: Chat context overflow
- 🔲 Bugs 5-8, 10-17: Medium/Low severity

---
