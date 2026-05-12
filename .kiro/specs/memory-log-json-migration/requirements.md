# Requirements Document

## Introduction

The TradingAgents memory system currently stores past decisions and reflections in a markdown file (`~/.tradingagents/memory/trading_memory.md`). This file is parsed with regex by the dashboard's History view return filter, the Portfolio Overview last-analysis join, and any future feature that needs return data. Markdown parsing is fragile — minor format changes break the parser silently. This feature migrates the authoritative memory data store to a JSON file (`trading_memory.json`) alongside the existing markdown file. The markdown file is retained for human readability but is no longer the source of truth for programmatic reads.

All changes are confined to `tradingagents/agents/utils/memory.py` and `dashboard/utils.py`. No agent prompts, LangGraph graph, or other pipeline code is changed.

**Dependencies:** None — this spec has no prerequisites and should be implemented early as other specs depend on it (History UX return filter, Portfolio Overview last-analysis join).

---

## Glossary

- **Memory_Log**: The persistent record of past trading decisions, reflections, and outcomes maintained by the TradingAgents system.
- **Markdown_File**: The existing `~/.tradingagents/memory/trading_memory.md` file, retained for human readability.
- **JSON_File**: The new `~/.tradingagents/memory/trading_memory.json` file that becomes the authoritative data source for programmatic reads.
- **Memory_Entry**: A single decision record containing fields: `ticker`, `date`, `rating`, `decision` (full text), `raw` (raw return float or null), `alpha` (alpha return float or null), `holding` (days int or null), `reflection` (string or null), `pending` (bool), and optionally `portfolio_context` (string or null).
- **TradingMemoryLog**: The existing class in `tradingagents/agents/utils/memory.py` responsible for reading and writing the Memory_Log.
- **load_memory_entries**: The existing function in `dashboard/utils.py` that returns a list of Memory_Entry dicts for the dashboard to consume.

---

## Requirements

### Requirement 1: JSON Memory File as Authoritative Store

**User Story:** As a developer, I want the memory log to be stored as JSON so that all dashboard features reading return data have a reliable, schema-validated source rather than a fragile markdown parser.

#### Acceptance Criteria

1. THE TradingMemoryLog class SHALL write all new memory entries to `~/.tradingagents/memory/trading_memory.json` using UTF-8 encoding, in addition to the existing Markdown_File.
2. THE JSON_File SHALL store entries as a JSON array under a top-level `"entries"` key, where each element is a Memory_Entry object.
3. WHEN the JSON_File does not exist, THE TradingMemoryLog class SHALL create it with an empty `{"entries": [], "schema_version": 1}` structure on first write.
4. WHEN the JSON_File exists but contains malformed JSON, THE TradingMemoryLog class SHALL:
   - Rename the corrupted file to `trading_memory.json.corrupt.{ISO-timestamp}` to preserve it for manual recovery.
   - Log a warning with the backup path.
   - Create a fresh JSON_File on the next write.
   - THE class SHALL NOT silently discard corrupted data.
5. THE TradingMemoryLog class SHALL continue writing the Markdown_File unchanged so that human-readable output is preserved.
6. ALL writes to the JSON_File SHALL use the atomic write pattern: write to a temporary file (`trading_memory.json.tmp`) in the same directory, then rename (move) the temporary file to the target path. This ensures that a crash or power loss mid-write never leaves a corrupted or partial JSON file.

---

### Requirement 2: Read from JSON, Fall Back to Markdown

**User Story:** As a developer, I want the system to read from the JSON file when available and fall back to the markdown parser only when the JSON file is absent, so that existing deployments without a JSON file continue to work during the migration period.

#### Acceptance Criteria

1. WHEN the JSON_File exists and is valid, THE `load_memory_entries()` function in `dashboard/utils.py` SHALL read Memory_Entries from the JSON_File and SHALL NOT invoke the markdown parser.
2. WHEN the JSON_File does not exist, THE `load_memory_entries()` function SHALL fall back to parsing the Markdown_File using the existing regex parser, preserving current behavior for existing deployments.
3. WHEN the JSON_File exists but contains malformed JSON, THE `load_memory_entries()` function SHALL fall back to parsing the Markdown_File, SHALL log a warning, and SHALL NOT attempt to repair or overwrite the JSON_File (that is the responsibility of TradingMemoryLog on next write).
4. THE `load_memory_entries()` function signature and return schema SHALL remain unchanged so that all callers (History view, Portfolio Overview) require no modification.

---

### Requirement 3: Migrate Existing Markdown Entries on First Run

**User Story:** As a user with existing memory log data, I want my past decisions and reflections to be available in the new JSON format automatically, so that I don't lose history when the migration runs.

#### Acceptance Criteria

1. WHEN the TradingMemoryLog class initialises and the JSON_File does not exist but the Markdown_File does, THE TradingMemoryLog class SHALL parse the Markdown_File, convert all entries to Memory_Entry objects, and write them to the JSON_File as a one-time migration.
2. WHEN the migration runs, THE TradingMemoryLog class SHALL log an informational message indicating how many entries were migrated and how many were skipped (if any).
3. WHEN individual entries fail to parse during migration (e.g., malformed markdown sections), THE TradingMemoryLog class SHALL skip those entries, log a warning per skipped entry with the line number or section identifier, and continue migrating the remaining entries. THE migration SHALL NOT be all-or-nothing for individual entry parse failures.
4. IF the migration fails catastrophically (e.g., filesystem write error, permission denied), THE TradingMemoryLog class SHALL leave the Markdown_File unchanged and SHALL NOT create a partial JSON_File. The atomic write pattern (write to `.tmp`, then rename) ensures this.
5. WHEN entries are skipped during migration, THE JSON_File SHALL include a top-level `"_migration_warnings"` field containing a list of strings describing what was skipped (e.g., `"Entry at line 45: could not parse date field"`).

**Implementation Note:** The migration SHALL use the atomic write pattern: write the complete JSON to a temporary file (e.g., `trading_memory.json.tmp`) in the same directory, then rename (move) the temporary file to the target path.

---

### Requirement 4: Schema Extensibility

**User Story:** As a developer, I want the JSON memory schema to accommodate future fields without breaking existing readers.

#### Acceptance Criteria

1. THE TradingMemoryLog class SHALL read Memory_Entry objects tolerantly, ignoring unknown fields, so that entries written by a future version can be read by the current version.
2. THE JSON_File schema SHALL support an optional `portfolio_context` field per entry (string or null) so that portfolio-aware runs can be identified in the memory log without a schema migration.
3. THE JSON_File SHALL include a top-level `"schema_version"` key set to `1` to support future migrations.

---

### Requirement 5: External Edit Policy

**User Story:** As a developer, I want a clear policy on what happens when the markdown file is edited externally after migration, so that there is no ambiguity about data drift.

#### Acceptance Criteria

1. AFTER migration, THE JSON_File SHALL be the authoritative source. Manual edits to the Markdown_File SHALL NOT be reflected in programmatic reads (since `load_memory_entries()` reads from JSON when it exists).
2. THE TradingMemoryLog class SHALL NOT attempt to detect or sync changes made to the Markdown_File after migration.
3. THE system SHALL provide a utility function `resync_from_markdown()` in `tradingagents/agents/utils/memory.py` that re-parses the Markdown_File and overwrites the JSON_File. This function SHALL be callable from a management script or test but SHALL NOT be called automatically during normal operation.
4. THE `resync_from_markdown()` function SHALL log a warning: "Overwriting JSON memory from markdown. Any JSON-only fields (e.g., portfolio_context) will be lost for entries not present in markdown."
