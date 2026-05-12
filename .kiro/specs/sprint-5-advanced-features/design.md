# Design Document — Sprint 5: Advanced Features (Chat Multi-Mode, Portfolio)

## Overview

Build the two most complex features that depend on all prior sprints: multi-analysis chat mode and portfolio management view.

## Analysis Chat Multi-Mode

### Architecture

```
Chat View
├── Mode Toggle: [Single] [Multi]
├── Single Mode (existing, unchanged)
│   └── One analysis selected → chat about it
└── Multi Mode (new)
    ├── Analysis Selector (multiselect, 2-5 analyses)
    ├── Combined Context Builder (merges all selected analyses into system prompt)
    ├── Chat Interface (same streaming UI)
    └── Persistence (SQLite chat_messages with mode='multi', conversation_id)
```

### Combined Context Builder

```python
def build_multi_context(analyses: List[Dict]) -> str:
    parts = ["You have access to multiple analyses. Compare and contrast them."]
    for i, data in enumerate(analyses, 1):
        parts.append(f"\n## Analysis {i}: {data['company_of_interest']} ({data['trade_date']})")
        parts.append(_build_context(data))  # reuse existing single-context builder
    return "\n".join(parts)
```

### Context Size Warning

Before building: estimate tokens. If > 50% of model limit, show warning. Still proceed (not a blocker).

### Persistence via SQLite

- `conversation_id = f"multi_{uuid4_short}"`
- Each message INSERT into `chat_messages` with `mode='multi'`, all selected tickers/dates
- Badge: `SELECT DISTINCT analysis_ticker, analysis_date FROM chat_messages WHERE mode='multi'`

### Selection Drop Behavior

When user deselects below 2: preserve history in session_state, disable input, show message. Re-selecting to 2+ resumes.

## Portfolio Management

### Architecture

```
Portfolio View
├── Sidebar: Add Position (ticker + shares + optional cost basis)
├── Main Area:
│   ├── Live Overview Table (positions + current prices + P&L + last analysis)
│   ├── Batch Analysis Section (select positions → run with WorkerPool)
│   └── Individual Analysis Drill-in (render_decision_first per position)
```

### Data Flow

1. **Positions** stored in SQLite `portfolio_positions` table (+ JSON backup)
2. **Live prices** fetched via `yf.download([tickers], period="1d")` batch call
3. **Last analysis** JOIN: `portfolio_positions LEFT JOIN analyses ON ticker`
4. **Batch analysis** uses `WorkerPool` from Sprint 4 with `portfolio_context` injected
5. **Portfolio context** string: "User holds {shares} shares of {ticker} at cost basis ${cost}. Current P&L: {pnl}%."

### Price Fetching Strategy

```python
tickers = [p["ticker"] for p in positions]
df = yf.download(tickers, period="1d", progress=False)
# Handle MultiIndex columns for multi-ticker
for ticker in tickers:
    price = df[("Close", ticker)].iloc[-1] if not pd.isna(...) else None
```

Fallback for NaN tickers: individual `yf.Ticker(t).info["currentPrice"]` calls.

### NTFS Atomic Write

Portfolio JSON backup uses: write to `.tmp` → `os.replace()` → on failure: retry 100ms → on second failure: direct write + log warning.

## Files Modified/Created

| File | Changes |
|------|---------|
| `dashboard/views/chat.py` | Major rewrite: mode toggle, multi-select, combined context, SQLite persistence |
| `dashboard/views/portfolio.py` | NEW — entire portfolio view |
| `streamlit_app.py` | Add "💼 Portfolio" nav entry |
| `dashboard/db.py` | Portfolio CRUD functions, chat message functions |
