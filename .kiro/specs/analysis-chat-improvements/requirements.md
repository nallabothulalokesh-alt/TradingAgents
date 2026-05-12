# Requirements Document

## Introduction

The Analysis Chat view in the TradingAgents Streamlit dashboard currently supports loading a single analysis at a time via a dropdown and chatting with an LLM about it. This feature adds a **Multi-Analysis Chat Mode** that lets users select multiple analyses — across different dates for the same ticker, or across entirely different tickers — and conduct a single unified LLM conversation covering all selected analyses. The existing single-analysis mode remains the default and is unchanged.

## Glossary

- **Chat_View**: The `dashboard/views/chat.py` Streamlit page, the primary surface being modified.
- **Single_Mode**: The existing default chat mode where one analysis is loaded via a dropdown and chatted about.
- **Multi_Mode**: The new opt-in mode where two or more analyses are selected and combined into one LLM conversation.
- **Analysis_Record**: A single saved analysis result, identified by a `<TICKER>|<DATE>` key, stored as a `full_states_log_<DATE>.json` file on disk.
- **Analysis_Key**: A string of the form `<TICKER>|<DATE>` that uniquely identifies one Analysis_Record (e.g. `NVDA|2026-01-15`).
- **Multi_Key**: A deterministic string that uniquely identifies a specific combination of selected analyses, formed by sorting the individual Analysis_Keys alphabetically and joining them with `+` (e.g. `AAPL|2026-03-01+NVDA|2026-01-15+NVDA|2026-02-01`).
- **Combined_Context**: A single system-prompt string built by concatenating the context of each selected analysis, each prefixed with a labeled section header.
- **Multi_Chat_Dir**: The directory `~/.tradingagents/logs/multi_chat/` where multi-analysis chat history files are stored.
- **Multi_Chat_File**: A JSON file inside Multi_Chat_Dir named `chat_history_<MULTI_KEY_HASH>.json`, where `<MULTI_KEY_HASH>` is a short SHA-256 hex digest of the Multi_Key.
- **Mode_Toggle**: A Streamlit toggle widget in the sidebar that switches the Chat_View between Single_Mode and Multi_Mode.
- **Ticker_Filter**: A text input in the sidebar (Multi_Mode only) used to filter the list of available Analysis_Records by ticker symbol substring.
- **Analysis_Selector**: A multiselect widget in the sidebar (Multi_Mode only) that displays the filtered Analysis_Records and allows the user to pick which ones to include.
- **Context_Builder**: The `_build_context()` function in `chat.py` that converts one Analysis_Record dict into a system-prompt string.
- **Multi_Context_Builder**: A new function `_build_multi_context()` in `chat.py` that calls Context_Builder for each selected analysis and concatenates the results with labeled section headers.
- **History_Utils**: The `load_chat_history()`, `save_chat_history()`, and `_cached_chat_msg_count()` helpers in `dashboard/utils.py`.

---

## Requirements

### Requirement 1: Mode Toggle

**User Story:** As a user, I want to switch between single-analysis and multi-analysis chat modes from the sidebar, so that I can choose the right mode for my current task without losing the default single-analysis experience.

#### Acceptance Criteria

1. THE Chat_View SHALL display a Mode_Toggle in the sidebar above the analysis selection controls.
2. WHEN the Chat_View first loads and no persisted mode preference exists, THE Mode_Toggle SHALL default to Single_Mode.
3. WHEN a persisted mode preference exists from a prior session, THE Mode_Toggle SHALL restore that preference on load.
4. WHEN the user changes the Mode_Toggle, THE Chat_View SHALL persist the selected mode so it is restored on the next session load.
5. WHEN the user activates Multi_Mode via the Mode_Toggle, THE Chat_View SHALL replace the single-analysis dropdown with the two-step Multi_Mode selection UI (Ticker_Filter + Analysis_Selector).
6. WHEN the user deactivates Multi_Mode via the Mode_Toggle, THE Chat_View SHALL restore the single-analysis dropdown and clear any multi-analysis session state.
7. THE Chat_View SHALL preserve the existing single-analysis dropdown, model selector, Clear Chat button, and Export button exactly as they are when Single_Mode is active.
8. WHEN the Chat_View loads and `st.session_state["chat_mode"]` is set to `"multi"` (e.g. navigated here from the Compare view or Multi-Ticker Analysis view), THE Chat_View SHALL automatically activate Multi_Mode regardless of any persisted mode preference, and SHALL clear the `"chat_mode"` key from session state after consuming it so that subsequent loads are not affected.

---

### Requirement 2: Two-Step Analysis Selection (Multi_Mode)

**User Story:** As a user, I want to first filter analyses by ticker and then pick specific ones from the filtered list, so that I can quickly find and select the analyses I care about without scrolling through a long unfiltered list.

#### Acceptance Criteria

1. WHEN Multi_Mode is active, THE Chat_View SHALL display a Ticker_Filter text input as Step 1 of the selection UI.
2. WHEN the Ticker_Filter is empty, THE Analysis_Selector SHALL display all available Analysis_Records.
3. WHEN the user types a string into the Ticker_Filter, THE Analysis_Selector SHALL display only Analysis_Records whose ticker symbol contains the entered string as a case-insensitive substring.
4. WHEN Multi_Mode is active, THE Chat_View SHALL display an Analysis_Selector as Step 2, showing the filtered Analysis_Records as selectable options.
5. THE Analysis_Selector SHALL label each option as `<TICKER> · <DATE> [<RATING>]`, matching the format used in the existing single-analysis dropdown.
6. THE Analysis_Selector SHALL allow the user to select zero or more Analysis_Records simultaneously.
7. WHEN fewer than two Analysis_Records are selected in the Analysis_Selector, THE Chat_View SHALL display an informational message prompting the user to select at least two analyses to start a multi-analysis chat. WHEN exactly one Analysis_Record is pre-selected (e.g. via `chat_multi_prefill` from History or Compare), the message SHALL be specific: `"1 analysis pre-selected. Add at least one more to start chatting."` WHEN zero analyses are selected, the message SHALL be: `"Select at least two analyses to start a multi-analysis chat."` THE Chat_View SHALL NOT attempt to auto-load any context or chat history when fewer than two analyses are selected.
8. WHEN two or more Analysis_Records are selected and the Combined_Context builds successfully, THE Chat_View SHALL load the Combined_Context and the corresponding multi-analysis chat history automatically without requiring an additional confirmation step.
9. WHEN two or more Analysis_Records are selected but the Combined_Context fails to build, THE Chat_View SHALL proceed with auto-loading the chat history only and display a warning that the analysis context could not be loaded.
10. WHEN the Chat_View loads in Multi_Mode and `st.session_state["chat_multi_prefill"]` is present and contains a non-empty list of Analysis_Keys, THE Chat_View SHALL pre-select those Analysis_Records in the Analysis_Selector (matching by Analysis_Key) and SHALL clear the `"chat_multi_prefill"` key from session state after consuming it. IF any Analysis_Key in the prefill list does not match an available Analysis_Record, THE Chat_View SHALL silently skip that key and pre-select only the matching records.
11. WHEN the selection drops from 2+ analyses to fewer than 2 (user deselects), THE Chat_View SHALL preserve the current chat history in `chat_multi_history` session state but SHALL disable the chat input and display: "Select at least 2 analyses to continue chatting." THE Chat_View SHALL NOT clear the history — if the user re-selects to 2+, the conversation resumes.

---

### Requirement 3: Combined Context Construction

**User Story:** As a user, I want the LLM to have clear, labeled access to all selected analyses in a single conversation, so that I can ask comparative or cross-analysis questions and receive accurate, well-attributed answers.

#### Acceptance Criteria

1. THE Multi_Context_Builder SHALL accept a list of Analysis_Record dicts and return a single Combined_Context string.
2. THE Multi_Context_Builder SHALL call Context_Builder for each Analysis_Record in the provided list.
3. THE Multi_Context_Builder SHALL prefix each individual context block with a section header of the form `## Analysis N: <TICKER> | <DATE>`, where N is the 1-based position of the analysis in the sorted selection order.
4. THE Multi_Context_Builder SHALL include a preamble instructing the LLM that multiple analyses are present, that each is clearly labeled, and that the LLM should reference the label when attributing information to a specific analysis.
5. THE Multi_Context_Builder SHALL sort the Analysis_Records by ticker then by date (ascending) before numbering them, so the order is deterministic regardless of the order the user selected them.
6. WHEN the Combined_Context is built, THE Chat_View SHALL store it in session state under the key `chat_multi_context_str`.
7. WHEN the Combined_Context exceeds 50% of the selected model's context window (estimated via words × 1.3 heuristic), THE Chat_View SHALL display a warning: "⚠️ Combined analysis context is very large ({estimated_tokens:,} tokens). Consider selecting fewer analyses or using a model with a larger context window (e.g., Gemini or Claude)." THE Chat_View SHALL still proceed with loading — this is a warning, not a blocker.

---

### Requirement 4: Multi-Analysis Chat History Persistence

**User Story:** As a user, I want my multi-analysis chat conversations to be saved and restored automatically, so that I can return to a cross-analysis conversation exactly where I left it.

#### Acceptance Criteria

1. THE Chat_View SHALL compute the Multi_Key by sorting the selected Analysis_Keys alphabetically and joining them with `+`.
2. THE Chat_View SHALL derive the Multi_Chat_File path by computing a SHA-256 hex digest of the Multi_Key (truncated to 16 characters) and using it as the filename: `chat_history_<HASH>.json` inside Multi_Chat_Dir.
3. WHEN Multi_Chat_Dir does not exist, THE Chat_View SHALL create it before attempting to write a Multi_Chat_File.
4. WHEN the set of selected analyses changes, THE Chat_View SHALL load the Multi_Chat_File for the new Multi_Key if it exists, or start with an empty history if it does not.
5. WHEN the user sends a message or receives a reply in Multi_Mode, THE Chat_View SHALL save the updated history to the Multi_Chat_File immediately after each exchange, matching the save behavior of Single_Mode.
6. IF writing the Multi_Chat_File fails for any reason, THEN THE Chat_View SHALL continue operating normally without displaying an error to the user, matching the existing silent-failure behavior of `save_chat_history()`.
7. THE Chat_View SHALL store the current multi-analysis history in session state under the key `chat_multi_history`.
8. THE Chat_View SHALL store the current Multi_Key in session state under the key `chat_multi_key`.

---

### Requirement 5: Multi-Mode Chat Conversation UI

**User Story:** As a user, I want the multi-analysis chat conversation to feel consistent with the single-analysis chat, so that I don't have to learn a new interface.

#### Acceptance Criteria

1. WHEN Multi_Mode is active and two or more analyses are selected, THE Chat_View SHALL render the conversation history, chat input, and streaming LLM responses using the same visual components and behavior as Single_Mode.
2. THE Chat_View SHALL display a header card summarizing the selected analyses (ticker symbols and dates) in place of the single-analysis card shown in Single_Mode.
3. WHEN the multi-analysis chat history is non-empty and has been restored from disk, THE Chat_View SHALL display the same "Restored N saved messages" notice used in Single_Mode.
4. WHEN the multi-analysis chat history is empty, THE Chat_View SHALL NOT display the suggested questions panel (suggested questions are a Single_Mode-only feature).
5. THE Chat_View SHALL use the same `_stream_llm()` function for Multi_Mode responses as for Single_Mode responses, passing the Combined_Context as the system prompt.
6. THE Chat_View SHALL display the chat input placeholder as `Ask anything about these N analyses…`, where N is the number of selected analyses.

---

### Requirement 6: Clear Chat and Export in Multi_Mode

**User Story:** As a user, I want to clear or export my multi-analysis chat history using the same controls I use in single-analysis mode, so that the experience is consistent.

#### Acceptance Criteria

1. WHEN Multi_Mode is active, THE Chat_View SHALL display the Clear Chat button in the sidebar.
2. WHEN the user clicks Clear Chat in Multi_Mode, IF the Multi_Chat_File write succeeds, THEN THE Chat_View SHALL set `chat_multi_history` to an empty list.
3. IF the Multi_Chat_File write fails when the user clicks Clear Chat in Multi_Mode, THEN THE Chat_View SHALL leave `chat_multi_history` intact and display an error message to the user.
4. WHEN Multi_Mode is active, THE Chat_View SHALL display the Export button in the sidebar.
5. WHEN the user clicks Export in Multi_Mode, THE Chat_View SHALL generate a downloadable text file containing the full multi-analysis conversation, with each message prefixed by its timestamp and role.
6. WHEN the number of selected analyses is 2 or fewer, THE Chat_View SHALL name the exported file `chat_multi_<TICKER1>_<TICKER2>_<DATE>.txt` using the tickers of all selected analyses and the current date. WHEN the number of selected analyses is 3 or more, THE Chat_View SHALL name the exported file `chat_multi_{N}tickers_{DATE}.txt` where N is the count of selected analyses, to avoid excessively long filenames.

---

### Requirement 7: Session State Isolation

**User Story:** As a developer, I want Single_Mode and Multi_Mode to use separate session state keys, so that switching between modes does not corrupt either conversation.

#### Acceptance Criteria

1. THE Chat_View SHALL use the session state keys `chat_analysis_key`, `chat_analysis_data`, `chat_analysis_file`, `chat_context_str`, and `chat_history` exclusively for Single_Mode, leaving them unchanged from the current implementation.
2. THE Chat_View SHALL use the session state keys `chat_multi_key`, `chat_multi_context_str`, `chat_multi_history`, and `chat_multi_files` exclusively for Multi_Mode.
3. WHEN the user switches from Multi_Mode to Single_Mode, THE Chat_View SHALL clear all `chat_multi_*` session state keys.
4. WHEN the user switches from Single_Mode to Multi_Mode, THE Chat_View SHALL NOT modify any `chat_analysis_*` or `chat_history` session state keys.

**Implementation Note (existing code):** The current Single_Mode implementation uses `chat_analysis_key`, `chat_analysis_data`, `chat_analysis_file`, `chat_context_str`, and `chat_history` in session state. The `chat_prefill_ticker` and `chat_prefill_date` keys are one-shot navigation hints consumed on load. When implementing Multi_Mode, ensure that the `_stream_llm()` function (shared between modes) does not write to any mode-specific session state key — it should only return the response text, and the caller should handle persistence to the appropriate history key (`chat_history` for single, `chat_multi_history` for multi).

---

### Requirement 8: Multi-Analysis History Badge in Analysis Selector

**User Story:** As a user, I want to see at a glance which analyses already have saved multi-analysis conversations, so that I can quickly resume previous cross-analysis sessions.

#### Acceptance Criteria

1. THE Analysis_Selector SHALL append a `💬` badge (presence indicator) to the label of each Analysis_Record that appears in at least one saved Multi_Chat_File.
2. WHEN no Multi_Chat_Files reference a given Analysis_Record, THE Analysis_Selector SHALL display that record's label without a badge.
3. THE Chat_View SHALL compute badge presence lazily during the sidebar render cycle, triggering computation only when the Analysis_Selector is being rendered, and SHALL cache the result for the duration of that render to avoid redundant disk reads.

**Design Note:** An earlier design used `💬<N>` showing total message count, but this grows unboundedly and becomes meaningless. A simple presence indicator (`💬` = has multi-chat history, no badge = doesn't) is clearer and cheaper to compute.

---

### Requirement 9: Multi-Chat Index File

**⚠️ SUPERSEDED by SQLite Data Layer spec Req 5.** Badge computation uses a SQL query (`SELECT DISTINCT analysis_ticker, analysis_date FROM chat_messages WHERE mode='multi'`) instead of a file-based index. The acceptance criteria below are retained for reference only — implementation uses SQLite.

**User Story:** As a developer, I want a lightweight index file that maps each Analysis_Key to its multi-chat conversations, so that badge counts are computed in O(1) rather than by scanning all multi-chat files on every render.

#### Acceptance Criteria

1. THE Chat_View SHALL maintain an index file at `~/.tradingagents/logs/multi_chat/index.json` with the schema `{"<ANALYSIS_KEY>": ["<HASH1>", "<HASH2>", ...], ...}` mapping each Analysis_Key to the list of Multi_Chat_File hashes that include it.
2. WHEN a new Multi_Chat_File is created or updated, THE Chat_View SHALL update the index file to add or refresh the entry for each Analysis_Key included in that Multi_Chat_File.
3. WHEN the Chat_View computes badge counts for the Analysis_Selector, THE Chat_View SHALL read the index file once and look up each Analysis_Key in O(1) rather than scanning all Multi_Chat_Files.
4. WHEN the index file does not exist, THE Chat_View SHALL treat all badges as absent (no `💬` shown) and SHALL create the index file on the next Multi_Chat_File write.
5. WHEN the index file exists but contains malformed JSON, THE Chat_View SHALL treat all badges as absent, log a warning, and overwrite the index file on the next Multi_Chat_File write.
6. IF writing the index file fails for any reason, THE Chat_View SHALL continue operating normally without displaying an error to the user.
7. WHEN reading the index for badge computation, THE Chat_View SHALL verify that referenced Multi_Chat_Files still exist on disk. IF a referenced file no longer exists, THE Chat_View SHALL remove that stale hash from the index entry lazily (on next index write) so that badges remain accurate after manual file deletions.

---

### Requirement 10: Context Window Management

**User Story:** As a user chatting about an analysis, I want the system to handle large contexts and long conversation histories gracefully, so that I don't encounter cryptic LLM errors when my conversation grows long or the analysis is very detailed.

#### Acceptance Criteria

1. THE Chat_View SHALL display the approximate context size (in words) when an analysis is loaded, using the existing `~{len(ctx.split()):,} words of analysis loaded` pattern.
2. WHEN the combined token count of the system prompt (analysis context) plus all chat history messages exceeds 80% of the selected model's context window, THE Chat_View SHALL display a warning: "⚠️ Conversation is approaching the model's context limit. Consider clearing chat history or switching to a model with a larger context window."
3. WHEN the combined token count would exceed the model's context window, THE Chat_View SHALL truncate the oldest chat history messages (keeping the system prompt and the most recent N messages) rather than sending an oversized request that will fail. THE Chat_View SHALL display an informational message: "ℹ️ Older messages were trimmed to fit the model's context window."
4. THE Chat_View SHALL estimate token counts using a simple heuristic (words × 1.3) rather than requiring a tokenizer dependency. Exact token counting is not required.
5. THE Chat_View SHALL define approximate context window sizes for known models: OpenAI gpt-4o/gpt-5.4 = 128K tokens, DeepSeek = 64K tokens, Anthropic Claude = 200K tokens, Google Gemini = 1M tokens, Ollama models = 8K tokens (conservative default). Unknown models SHALL use 8K as the default.

**Bug Fix Note (existing code):** The current `_stream_llm()` sends ALL chat history messages to the LLM on every call with no truncation. With 100+ messages, this can easily exceed context limits for smaller models, causing API errors that surface as "❌ LLM error: ..." in the chat.

---

### Requirement 11: Prefill Validation on Navigation

**User Story:** As a user navigating to Chat from History or Watchlist, I want to see a clear message if the target analysis cannot be found, rather than silently loading a different analysis.

#### Acceptance Criteria

1. WHEN the Chat_View loads with `chat_prefill_ticker` and `chat_prefill_date` set, and no matching Analysis_Record is found in `list_history()`, THE Chat_View SHALL display an informational message: "The analysis for {ticker} on {date} could not be found. It may have been deleted or moved." THE Chat_View SHALL NOT silently select a different analysis.
2. WHEN the prefill target is not found, THE Chat_View SHALL leave the analysis dropdown at its default position (no selection) and SHALL NOT auto-load any context.
3. WHEN the prefill target IS found, THE Chat_View SHALL select it in the dropdown and load its context, matching current behavior.

**Bug Fix Note (existing code):** The current code uses `next((i for i, r in enumerate(records) if ...), 0)` which falls back to index 0 (first analysis) when the target isn't found. This silently loads the wrong analysis with no indication to the user.
