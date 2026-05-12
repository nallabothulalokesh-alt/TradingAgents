# Tasks — Sprint 1A: Parallel Analyst Execution

## Task 1: Add `parallel_analysts` config key
- [ ] Add `"parallel_analysts": True` to `DEFAULT_CONFIG` in `tradingagents/default_config.py`
- [ ] Add `"parallel_analysts": True` to `DASHBOARD_CONFIG` in `dashboard/utils.py`

## Task 2: Create `_build_analyst_subgraph()` helper
- [ ] In `tradingagents/graph/setup.py`, add function `_build_analyst_subgraph(analyst_type, analyst_node, tool_node, conditional_fn)` that returns a compiled subgraph
- [ ] The subgraph StateGraph uses `AgentState` and wires: START → Analyst → (tools loop) → Msg Clear → END
- [ ] The subgraph's conditional edge uses the existing `should_continue_{type}` function
- [ ] Test: compile a market analyst subgraph and verify node set is correct

## Task 3: Create `_make_analyst_wrapper()` helper
- [ ] In `tradingagents/graph/setup.py`, add function `_make_analyst_wrapper(subgraph, report_field, analyst_type)` that returns a parent-graph node function
- [ ] The wrapper builds initial state with `{messages: [("human", company)], company_of_interest, trade_date}`
- [ ] The wrapper invokes the subgraph and returns `{report_field: result}`
- [ ] The wrapper catches exceptions and returns `{report_field: "", warnings: [...]}`
- [ ] Test: invoke wrapper with mock state, verify it returns the report field

## Task 4: Rewrite `setup_graph()` for parallel mode
- [ ] When `self.config.get("parallel_analysts", True)` is True:
  - Build a subgraph per selected analyst using `_build_analyst_subgraph()`
  - Create wrapper nodes using `_make_analyst_wrapper()`
  - Add wrapper nodes to parent graph
  - Add edges: START → each wrapper node
  - Add `"Analyst Barrier"` node (lambda state: state)
  - Add edges: each wrapper → Analyst Barrier
  - Add edge: Analyst Barrier → Bull Researcher
- [ ] When `parallel_analysts` is False: use existing sequential chain (current code)
- [ ] Keep all post-analyst nodes unchanged (Bull/Bear, Research Manager, Trader, Risk, PM)
- [ ] Test: compile graph in parallel mode, verify node names and edge structure

## Task 5: Pass config to `GraphSetup`
- [ ] Modify `GraphSetup.__init__()` to accept `config` parameter
- [ ] Pass `config` from `TradingAgentsGraph.__init__()` to `GraphSetup`
- [ ] `setup_graph()` reads `self.config.get("parallel_analysts", True)` to decide mode

## Task 6: Update `_build_fast_graph()` for parallel
- [ ] In `dashboard/runner.py`, modify `_build_fast_graph()` to use subgraph pattern for fast-mode analysts (market, news, social)
- [ ] Barrier connects to Trader (not Bull Researcher) — same as current behavior
- [ ] When `config.get("parallel_analysts", True)` is False, keep sequential (current code)
- [ ] Test: build fast graph in parallel mode, verify Trader is reachable from barrier

## Task 7: Fix progress tracking for parallel analysts
- [ ] In `runner.py` `_update_from_state()`, update the "first analyst running" logic:
  - When parallel mode: mark ALL selected analysts as "running" at first state snapshot (not just one)
- [ ] Verify that multiple report fields appearing in one snapshot are all detected (existing loop handles this)

## Task 8: Add sequential fallback config to dashboard
- [ ] In `dashboard/views/single_ticker.py` sidebar, optionally expose a "Parallel analysts" toggle (or keep it config-only for now)
- [ ] Pass `parallel_analysts` through the config dict to `run_analysis()` → `TradingAgentsGraph`

## Task 9: Write tests
- [ ] Test: `setup_graph()` with `parallel_analysts=True` produces graph with wrapper nodes + barrier
- [ ] Test: `setup_graph()` with `parallel_analysts=False` produces sequential graph (regression)
- [ ] Test: Analyst subgraph handles tool-call loop correctly (mock tool returns data)
- [ ] Test: Analyst subgraph wrapper catches exception and returns empty report + warning
- [ ] Test: Full pipeline with parallel analysts produces same `final_state` fields as sequential (integration test)
- [ ] Test: Fast Mode parallel graph connects barrier → Trader (not Bull Researcher)

## Task 10: Dashboard warning display for analyst failures
- [ ] In `dashboard/views/single_ticker.py`: check `snap["warnings"]` list on each render
- [ ] For each warning: display `st.warning(warning, icon="⚠️")` above the reports section
- [ ] In `_render_progress()`: show failed analysts with red "❌" icon and "failed" status
- [ ] Test: simulate analyst failure → warning appears in UI, other analysts still complete
