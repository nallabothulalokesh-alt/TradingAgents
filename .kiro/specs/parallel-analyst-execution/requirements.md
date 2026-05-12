# Requirements Document — Parallel Analyst Execution

## Introduction

The TradingAgents pipeline currently executes analysts **sequentially**: Market Analyst → News Analyst → Fundamentals Analyst → Social Analyst (if selected). Each analyst makes 1-3 tool calls to fetch data (yfinance/Alpha Vantage), then generates a report via LLM. The total analyst phase takes 60-120 seconds because each analyst waits for the previous one to finish — even though they are completely independent (no analyst reads another analyst's output).

This spec changes the analyst phase to run **all selected analysts concurrently**. Since each analyst operates on independent state fields (`market_report`, `news_report`, `fundamentals_report`, `sentiment_report`) and uses independent tool nodes, they can safely execute in parallel. The downstream phases (Research Debate → Trader → Risk Debate → Portfolio Manager) remain sequential as they depend on all analyst outputs.

**Scope:** `tradingagents/graph/setup.py` (graph construction), `tradingagents/graph/trading_graph.py` (minor), `tradingagents/agents/utils/agent_states.py` (no changes needed — state fields are already independent). No changes to agent prompts, data sources, dashboard, or persistence.

**Expected Impact:** Analyst phase drops from 60-120s (sequential) to 20-40s (parallel, bounded by the slowest analyst). Total pipeline time reduced by ~40-60%.

**Dependencies:** None — this is a pipeline-internal change with no dashboard or persistence dependencies. Can be implemented at any phase.

---

## Glossary

- **Analyst_Phase**: The portion of the LangGraph pipeline where Market, News, Fundamentals, and Social analysts fetch data and generate reports.
- **Fan-Out**: LangGraph pattern where a single node dispatches work to multiple parallel branches.
- **Fan-In**: LangGraph pattern where multiple parallel branches converge into a single downstream node.
- **Parallel_Branch**: One analyst's complete execution path: Analyst Node → (tool call loop) → Msg Clear Node.
- **Barrier_Node**: A no-op node that serves as the convergence point after all parallel branches complete. LangGraph automatically waits for all incoming edges before executing a node with multiple predecessors.
- **Tool_Call_Loop**: The conditional edge pattern where an analyst node either calls a tool (loops back to itself via the tool node) or finishes (proceeds to Msg Clear).
- **Selected_Analysts**: The user-configured list of analysts to include (subset of `["market", "news", "fundamentals", "social"]`).

---

## Requirements

### Requirement 1: Parallel Fan-Out from START to All Analysts

**User Story:** As a user, I want all selected analysts to begin fetching data simultaneously when I start an analysis, so that the total wait time is determined by the slowest analyst rather than the sum of all analysts.

#### Acceptance Criteria

1. THE `GraphSetup.setup_graph()` method SHALL connect `START` to ALL selected analyst nodes simultaneously (fan-out), rather than connecting them in a chain.
2. WHEN `selected_analysts = ["market", "news", "fundamentals", "social"]`, THE graph SHALL have edges:
   - `START → Market Analyst`
   - `START → News Analyst`
   - `START → Fundamentals Analyst`
   - `START → Social Analyst`
3. EACH analyst's tool-call loop SHALL remain unchanged: `Analyst Node ↔ tools_{type}` (conditional edge), then `Analyst Node → Msg Clear {Type}` when done.
4. THE parallel branches SHALL be independent — no analyst node reads or writes state fields belonging to another analyst.
5. WHEN only a subset of analysts is selected (e.g., `["market", "fundamentals"]`), THE graph SHALL fan-out only to those analysts.

---

### Requirement 2: Fan-In Barrier Before Research Debate

**User Story:** As a developer, I want the pipeline to wait for ALL analysts to complete before starting the Research Debate, so that the Bull/Bear researchers have all reports available.

#### Acceptance Criteria

1. THE `GraphSetup.setup_graph()` method SHALL add a barrier node named `"Analyst Barrier"` that serves as the convergence point for all parallel analyst branches.
2. EACH analyst's `Msg Clear {Type}` node SHALL have an edge to `"Analyst Barrier"`.
3. THE `"Analyst Barrier"` node SHALL have an edge to `"Bull Researcher"` (the first node of the Research Debate phase).
4. THE `"Analyst Barrier"` node SHALL be a no-op function that simply returns the state unchanged: `lambda state: state`. LangGraph's execution semantics guarantee that a node with multiple incoming edges waits for ALL predecessors to complete before executing.
5. WHEN only one analyst is selected, THE barrier node SHALL still be present (single incoming edge) to maintain a consistent graph structure.
6. THE Research Debate, Trader, Risk Debate, and Portfolio Manager phases SHALL remain unchanged — they execute sequentially after the barrier.

---

### Requirement 3: State Isolation Between Parallel Analysts

**User Story:** As a developer, I want confidence that parallel analysts don't corrupt each other's state, so that reports are always complete and correct.

#### Acceptance Criteria

1. EACH analyst SHALL write ONLY to its designated state field:
   - Market Analyst → `state["market_report"]`
   - News Analyst → `state["news_report"]`
   - Fundamentals Analyst → `state["fundamentals_report"]`
   - Social Analyst → `state["sentiment_report"]`
2. EACH analyst SHALL read ONLY `state["company_of_interest"]`, `state["trade_date"]`, and `state["messages"]` (for tool call mechanics).
3. THE `messages` field uses LangGraph's `MessagesState` annotation which handles concurrent appends via the `add_messages` reducer — this is safe for parallel tool-call message accumulation.
4. NO analyst SHALL read another analyst's report field. If an analyst's prompt currently references other reports (verify this), it SHALL be updated to remove that reference.
5. THE `Msg Clear` nodes SHALL only delete messages from the `messages` list — they SHALL NOT modify any report fields.

---

### Requirement 4: Fast Mode Parallel Execution

**User Story:** As a user running Fast Mode (reusing prior fundamentals), I want the remaining analysts to still run in parallel, so that Fast Mode is even faster.

#### Acceptance Criteria

1. THE `_build_fast_graph()` function in `dashboard/runner.py` SHALL use the same fan-out/barrier pattern for the analysts that ARE selected in Fast Mode.
2. WHEN Fast Mode skips certain analysts (e.g., fundamentals is reused), THE fan-out SHALL only include the analysts that need to run fresh.
3. THE pre-seeded state fields (e.g., `fundamentals_report` from a prior run) SHALL be present in the initial state BEFORE the graph starts, so the barrier node passes them through to the Research Debate unchanged.
4. THE Fast Mode graph SHALL still skip the Research Debate (Bull/Bear/Research Manager) as currently implemented — the barrier connects directly to the Trader node in Fast Mode.

---

### Requirement 5: Progress Tracking for Parallel Analysts

**User Story:** As a user watching the dashboard during an analysis, I want to see which analysts are running, which have completed, and which are still in progress, so that I understand what's happening.

#### Acceptance Criteria

1. THE callback mechanism (used by `dashboard/runner.py` to track `agent_status`) SHALL correctly report parallel analyst progress.
2. WHEN multiple analysts are running simultaneously, THE `agent_status` dict SHALL show all active analysts with status `"running"` concurrently, rather than showing only one at a time.
3. WHEN an analyst completes (its `Msg Clear` node fires), THE `agent_status` SHALL update that analyst to `"done"` while others may still show `"running"`.
4. THE dashboard's progress display (Single Ticker view timeline stepper) SHALL handle multiple simultaneous `"running"` entries — displaying them as parallel tracks rather than a single sequential list.
5. THE `RunState.snapshot()` method SHALL correctly capture the parallel state — multiple agents can be `"running"` simultaneously in the snapshot.

---

### Requirement 6: Error Handling in Parallel Branches

**User Story:** As a user, I want the analysis to complete even if one analyst fails (e.g., yfinance rate limit), degrading gracefully rather than crashing the entire pipeline.

#### Acceptance Criteria

1. WHEN an analyst's tool call fails (exception in the tool node), THE analyst branch SHALL catch the exception, write a warning to `state["warnings"]`, set its report field to an empty string, and proceed to its `Msg Clear` node.
2. THE failure of one analyst branch SHALL NOT prevent other parallel branches from completing.
3. THE barrier node SHALL proceed to the Research Debate even if one or more analyst reports are empty — the downstream agents already handle missing reports gracefully (they note "no {type} data available").
4. WHEN an analyst branch fails, THE dashboard SHALL display a warning: "⚠️ {Analyst_Name} failed: {error_message}. Analysis continues with available data."
5. THE `agent_status` for a failed analyst SHALL show `"failed"` (not `"done"`) so the UI can render it distinctly (e.g., red indicator vs green).
6. WHEN ALL analyst branches fail, THE pipeline SHALL still proceed to the Research Debate with empty reports — the Portfolio Manager will produce a low-conviction "Insufficient Data" decision rather than crashing.

---

### Requirement 7: LangGraph Implementation Details

**User Story:** As a developer, I want clear guidance on how to implement fan-out/fan-in in LangGraph, so that the implementation is correct and maintainable.

**Critical Design Decision:** Each analyst MUST run as an isolated **subgraph** because `create_msg_delete()` clears ALL messages from state. Without isolation, parallel analysts would delete each other's in-flight tool-call messages. Subgraphs give each analyst its own `messages` state that doesn't leak to other branches.

#### Acceptance Criteria

1. THE implementation SHALL use LangGraph's **subgraph** pattern: each analyst is compiled into its own `StateGraph` with isolated `messages` state.
2. EACH analyst subgraph SHALL:
   - Accept input state containing `company_of_interest` and `trade_date`
   - Have its own `messages` list (isolated from other analysts)
   - Contain: Analyst Node ↔ tools_{type} (conditional loop) → Msg Clear → END
   - Return output state containing only its report field (e.g., `{"market_report": "..."}`)
3. THE parent graph SHALL:
   - Fan out from START to all analyst subgraph nodes simultaneously
   - Each subgraph node wraps the compiled analyst subgraph
   - All subgraph nodes connect to the `"Analyst Barrier"` node
   - The barrier node merges all report fields into the parent state
4. THE parent graph structure SHALL be:
   ```python
   # Parent graph (simplified):
   # START → run_market_subgraph (parallel)
   # START → run_news_subgraph (parallel)
   # START → run_fundamentals_subgraph (parallel)
   # START → run_social_subgraph (parallel)
   # run_market_subgraph → Analyst Barrier
   # run_news_subgraph → Analyst Barrier
   # run_fundamentals_subgraph → Analyst Barrier
   # run_social_subgraph → Analyst Barrier
   # Analyst Barrier → Bull Researcher
   ```
5. EACH analyst subgraph wrapper node SHALL be a function that:
   - Extracts `company_of_interest` and `trade_date` from parent state
   - Invokes the compiled subgraph
   - Returns `{report_field: final_subgraph_state[report_field]}`
6. THE conditional edges for tool-call loops SHALL remain INSIDE each subgraph (unchanged from current implementation).
7. THE `create_msg_delete()` function SHALL NOT be modified — it continues to clear all messages within its subgraph's isolated state.

---

### Requirement 8: Backward Compatibility

**User Story:** As a developer, I want the parallel execution to be transparent to all downstream code — no other module should need changes.

#### Acceptance Criteria

1. THE `AgentState` TypedDict SHALL NOT be modified — the existing fields already support parallel writes (each analyst writes to a different field).
2. THE `propagate()` and `_run_graph()` methods in `TradingAgentsGraph` SHALL NOT be modified — they invoke the compiled graph the same way regardless of internal parallelism.
3. THE `final_state` dict returned by the graph SHALL have the same structure as before — all four report fields populated (or empty if analyst was not selected/failed).
4. THE `_log_state()` method SHALL NOT be modified — it reads the same fields from `final_state`.
5. THE `ConditionalLogic` class SHALL NOT be modified — each analyst's `should_continue_{type}` function operates independently.
6. ALL existing tests that invoke the graph SHALL pass without modification.
7. THE `selected_analysts` parameter to `setup_graph()` SHALL retain its current interface — the caller does not need to know whether execution is parallel or sequential.

---

### Requirement 9: Configuration Option for Sequential Fallback

**User Story:** As a developer debugging the pipeline, I want the option to force sequential analyst execution for easier debugging and log readability.

#### Acceptance Criteria

1. THE `DEFAULT_CONFIG` dict SHALL include a new key: `"parallel_analysts": True` (default enabled).
2. WHEN `config["parallel_analysts"]` is `False`, THE `setup_graph()` method SHALL use the original sequential chain (START → Analyst1 → Clear1 → Analyst2 → Clear2 → ... → Bull Researcher).
3. WHEN `config["parallel_analysts"]` is `True` (default), THE `setup_graph()` method SHALL use the fan-out/barrier pattern.
4. THE dashboard settings (if exposed) MAY include a toggle for this, but it is NOT required for this spec — the config dict is sufficient.
5. THE sequential fallback SHALL produce identical results to parallel execution (same final_state) — only the execution order and timing differ.
