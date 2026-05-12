# Tasks — Sprint 5: Advanced Features (Chat Multi-Mode, Portfolio)

## Analysis Chat Multi-Mode

### Task 1: Mode toggle UI
- [ ] Add mode selector at top of chat sidebar: `st.radio("Mode", ["Single", "Multi"])`
- [ ] When "Single": show existing single-analysis dropdown (unchanged)
- [ ] When "Multi": show multiselect widget for analyses (2-5 selections)
- [ ] Persist mode in `st.session_state["chat_mode"]`

### Task 2: Multi-analysis selector
- [ ] Use `st.multiselect()` with analysis labels from `list_history_summary()`
- [ ] Limit to 5 selections max
- [ ] Show 💬 badge for analyses that have existing multi-chat history (SQLite query)
- [ ] Handle `chat_multi_prefill` from Compare view (pre-select those analyses)

### Task 3: Combined context builder
- [ ] Implement `build_multi_context(analyses: List[Dict]) -> str` in `chat.py`
- [ ] Merge all selected analyses into one system prompt with clear section headers
- [ ] Estimate token count; if > 50% of model limit: show `st.warning()`
- [ ] Store in `st.session_state["chat_multi_context_str"]`

### Task 4: Multi-mode chat interface
- [ ] Reuse existing chat UI (message display, input, streaming)
- [ ] System prompt = combined context (instead of single analysis context)
- [ ] Chat history stored in `st.session_state["chat_multi_history"]`

### Task 5: Multi-mode persistence (SQLite)
- [ ] On each message: INSERT into `chat_messages` with `mode='multi'`, `conversation_id`
- [ ] Generate `conversation_id` on first message of a new multi-chat session
- [ ] Load history from SQLite when resuming (match by selected analysis keys)
- [ ] Dual-write to JSON file for portability

### Task 6: Selection drop behavior
- [ ] When selections drop below 2: disable chat input, show message
- [ ] Preserve `chat_multi_history` in session_state (don't clear)
- [ ] When selections restored to 2+: re-enable input, conversation resumes

### Task 7: Badge computation
- [ ] Query: `SELECT DISTINCT analysis_ticker, analysis_date FROM chat_messages WHERE mode='multi'`
- [ ] For each analysis in the multiselect options: show 💬 if it appears in results
- [ ] Cache result for duration of render cycle

## Portfolio Management

### Task 8: Create `dashboard/views/portfolio.py`
- [ ] Implement `render_portfolio()` function
- [ ] Add to `streamlit_app.py` navigation: "💼 Portfolio"
- [ ] Basic layout: sidebar for adding positions, main area for overview

### Task 9: Portfolio CRUD in `dashboard/db.py`
- [ ] `add_position(ticker, shares, cost_basis=None)` — INSERT into portfolio_positions
- [ ] `update_position(ticker, shares)` — UPDATE shares + updated_at
- [ ] `remove_position(ticker)` — DELETE from portfolio_positions
- [ ] `list_positions()` — SELECT all, LEFT JOIN with latest analysis for each ticker
- [ ] Dual-write to `~/.tradingagents/portfolio/portfolio.json` backup
- [ ] NTFS atomic write with retry for JSON backup
- [ ] Test: add, update, remove, list — verify both SQLite and JSON

### Task 10: Add Position UI
- [ ] Sidebar: ticker input + shares input + optional cost basis
- [ ] Validate ticker before adding (reuse `validate_ticker()`)
- [ ] If ticker exists: show warning preview "⚠️ You currently hold X shares. Submitting will replace."
- [ ] On submit: call `add_position()` or `update_position()`
- [ ] Show success/error message

### Task 11: Live Overview Table
- [ ] Fetch current prices via `yf.download(tickers, period="1d")`
- [ ] Handle NaN fallback (individual fetch for failed tickers)
- [ ] Calculate: current_value, cost_value (if cost_basis), P&L %, allocation %
- [ ] Render table with colored P&L (green positive, red negative)
- [ ] Show last analysis date + rating per position (from SQLite JOIN)
- [ ] Show loading spinner during price fetch

### Task 12: Batch Analysis
- [ ] "Analyze Selected" button (multiselect which positions to analyze)
- [ ] "Analyze All" button
- [ ] Use `WorkerPool` from `dashboard/worker_pool.py`
- [ ] Inject `portfolio_context` per ticker: "User holds {shares} shares..."
- [ ] Show progress (reuse Multi-Ticker progress pattern)
- [ ] Results appear inline per position

### Task 13: Individual Analysis Drill-in
- [ ] Per position: "View Last Analysis" expander
- [ ] Load full data via `load_run()` or `get_analysis_reports()` from SQLite
- [ ] Render with `render_decision_first()`
- [ ] "Run Fresh Analysis" button per position

### Task 14: Remove Position
- [ ] Per position in overview: "🗑" button
- [ ] Confirmation: "Remove NVDA from portfolio?"
- [ ] Call `remove_position(ticker)`
- [ ] Refresh view

### Task 15: Clear Chat and Export in Multi-Mode (Chat Req 6)
- [ ] "Clear Chat" button in Multi-Mode: clears `chat_multi_history`, deletes from SQLite
- [ ] "Export" button: downloads multi-chat as .txt file (same format as single-mode export)
- [ ] Both buttons in sidebar, same position as single-mode

### Task 16: "Open in Multi-Chat" from History (History Req 10)
- [ ] In History detail panel: add "💬 Open in Multi-Chat" button
- [ ] On click: set `chat_multi_prefill = [analysis_key]`, navigate to Chat in Multi mode
- [ ] User then adds more analyses in the Chat view to start comparing

### Task 17: Portfolio-Aware Run Badge in History (History Req 6)
- [ ] In History summary table: if analysis has `portfolio_context` field, show "🏦" badge
- [ ] Badge indicates this run was portfolio-aware (had position context injected)
- [ ] Query from SQLite: `WHERE portfolio_context IS NOT NULL`

### Task 18: Clickable Last-Analysis Badge in Portfolio (Portfolio Req 13)
- [ ] In Portfolio overview table: "Last Analysis" column shows date + rating
- [ ] Clicking it navigates to History view with ticker filter pre-set
- [ ] Set `st.session_state["hist_search"] = ticker`, navigate to History
