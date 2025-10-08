# pctl - PAIC Control CLI

> **This is the single source of truth for the current implementation plan and status, with high level guide.**

## Project Philosophy

**pctl is a real-world problem-solving toolkit for PAIC (PingOne Advanced Identity Cloud), not an infrastructure-as-code tool.**

### Why pctl exists vs Frodo
- **Frodo**: Infrastructure as Code - config management, deployment automation
- **pctl**: Operational tooling - debugging, testing, analysis, problem-solving

### Core Principles
1. **Problem-driven development** - Build features when facing real problems
2. **Incremental foundations** - Build shared code only when patterns emerge
3. **Total control** - Own the full stack for operational needs
4. **Lean architecture** - Avoid over-engineering, build what we need

### Use Cases
- Get service account tokens for API testing
- Test authentication journeys interactively
- Stream PAIC logs to local ELK for debugging
- Search historical logs for incident analysis
- Analyze journey performance and config changes
- **Future**: Whatever operational problems we encounter

## Current Implementation Plan

**Unified Python CLI** merging authflow (TS) + plctl.sh (Bash) into `pctl` with five subcommands:
- `pctl token` - JWT/access token management
- `pctl journey` - Authentication flow testing
- `pctl elk` - Local ELK stack management (log streaming to Elasticsearch)
- `pctl conn` - Connection profile management (service accounts, credentials)
- `pctl log` - Historical log analysis and searching ✅ **IMPLEMENTED**

## CLI Command Pattern

**Consistent pattern across all subcommands:**
```
pctl <subcommand> <action> <conn_name> [options]
```

**Examples:**
- `pctl conn add myenv --platform https://example.com --sa-id abc123`
- `pctl conn validate myenv`
- `pctl token get myenv --format bearer`
- `pctl log search myenv --days 7 -q '/payload/objectId co "endpoint/"'`
- `pctl elk start myenv`

## Tech Stack

- **UV** - Python package manager
- **Click** - CLI framework with nested subcommands
- **Pydantic** - Config validation and type safety
- **Rich** - Terminal UI and progress bars
- **asyncio** - Non-blocking subprocess calls
- **PyYAML, httpx, loguru** - Config, HTTP, logging
- **PyInstaller** - Single binary distribution

## Architecture

### 3-Layer Design
1. **CLI Layer** - External user interface (Click commands)
2. **Service Layer** - Internal API for cross-command communication  
3. **Core Layer** - Foundation utilities (config, HTTP, logging)

### Communication Rules
- **CLI Layer** → Service layer only
- **Service Layer** → Core shared utilities + own domain core + other services
- **Cross-command calls** → Service layer only
- **Domain boundaries**: Services access only `core/*` (shared), `core/{own_domain}/`, `services/*`

### Layer Responsibilities
- **Core Layer**: Data persistence, basic validation, infrastructure (files, HTTP, config)
- **Service Layer**: Business logic, workflows, cross-service coordination, user prompting
- **CLI Layer**: Command parsing, output formatting, user experience

### Data Flow Patterns
- **Core Layer**: Rich objects with methods and validation (internal domain logic)
- **Service Layer**: JSON/dict for cross-service communication (clean contracts)
- **CLI Layer**: Formatted output for users (tables, JSON, etc.)

## Project Structure

```
pctl/
├── pyproject.toml
├── pctl/
│   ├── cli/                    # 🖥️ CLI Layer
│   │   ├── main.py             # Click entry point
│   │   ├── token.py            # Token commands
│   │   ├── journey.py          # Journey commands
│   │   ├── elk.py              # ELK commands
│   │   └── conn.py             # Connection profile commands
│   ├── services/               # 🔄 Service Layer (Internal API)
│   │   ├── token/              # Token business logic
│   │   ├── journey/            # Journey business logic
│   │   ├── elk/                # ELK business logic
│   │   └── conn/               # Connection profile business logic
│   ├── core/                   # ⚙️ Core Layer (Foundation)
│   │   ├── config.py           # Shared: Configuration loading utilities
│   │   ├── http_client.py      # Shared: HTTP utilities
│   │   ├── logger.py           # Shared: Logging setup
│   │   ├── exceptions.py       # Shared: Custom exceptions
│   │   ├── process_manager.py  # Shared: Unified process management
│   │   ├── version.py          # Shared: Dynamic version reading from pyproject.toml
│   │   ├── token/              # Domain: Token-specific models and utilities
│   │   ├── elk/                # Domain: ELK-specific models and utilities
│   │   └── conn/               # Domain: Connection profile models and utilities
│   └── configs/                # YAML configurations
├── tests/
└── examples/                   # Legacy reference tools (ignore during development)
```

## Cross-Command Communication

- `pctl journey run` → `TokenService.get_token()` internally
- `pctl elk start` → `ConfigLoader.load_yaml()`
- All commands → `ConfigLoader` for YAML parsing
- Services can call each other, CLI cannot

## Development Commands

### Basic Testing
```bash
# Test CLI is working
uv run pctl --help
uv run pctl version

# Run with development dependencies
uv sync
```

### Development Workflow
```bash
# Run tests
uv run pytest

# Format code
uv run black .

# Lint code  
uv run ruff check .

# Install in development mode
uv sync
```

### Packaging
```bash
# Build single executable
uv run pyinstaller --onefile pctl/cli/main.py

# Output will be in: dist/main
```

## Current Status

- **Phase**: IDM-Config Change Tracking ✅ **COMPLETE**
- **Version**: 0.6.2 - Universal change tracking model for IDM-Config (6 types supported)
- **Complete**:
  - ✅ **Project Setup**: UV, 3-layer architecture, Python distribution
  - ✅ **Connection Subcommand**: Profile management (add, list, show, delete, validate), dual input modes (flags/config)
  - ✅ **Connection Foundations**: Core layer (conn_models, conn_manager), Service layer (ConnectionService)
  - ✅ **Token Subcommand**: JWT creation, ForgeRock token exchange, profile-based authentication
  - ✅ **Service Integration**: ConnectionService ↔ TokenService cross-service communication
  - ✅ **Validation Workflow**: Automatic validation on add, manual validation, validation status tracking
  - ✅ **Consistent CLI Pattern**: `pctl <subcommand> <action> <conn_name>` across all commands
  - ✅ **Journey Subcommand**: Complete authentication flow testing, step mode, config management
  - ✅ **ELK Subcommand**: 9 commands, log streaming via direct API calls, registry-based process management
  - ✅ **Dynamic Versioning**: Single source of truth from pyproject.toml
  - ✅ **HTTPClient Modernization**: Rich HTTPResponse objects, status code access, unified request methods
  - ✅ **ELK Service Enhancement**: Updated to use new HTTPClient methods, fixed status display issues
  - ✅ **ProcessManager**: Unified process management, clean Python interface, no argparse in workers
  - ✅ **Log Search Command**: Complete historical log fetching with pagination, filtering, and multi-day queries
  - ✅ **Service Layer Dict Contract**: Clean JSON/dict interface, no core model leakage to CLI
  - ✅ **Universal Change Model**: Single ConfigChangeEvent model for all resource types (IDM + AM)
  - ✅ **IDM-Config Change Tracking**: 6 resource types - endpoint, connector, emailTemplate, mapping, access, repo
  - ✅ **Resource Mappings**: Pattern 1 (type/name) and Pattern 2 (type only) support
  - ✅ **Enhanced Metadata**: conn_name, source, resource_type/name in all outputs
  - ✅ **Three Output Formats**: jsonl (compact), json (metadata), js (string arrays like Frodo)
  - ✅ **Auto Directory Creation**: Output files automatically create parent directories
- **Current Work** (Phase 5 - Future Features):
  - 📋 **AM-Config Change Tracking**: Add support for journeys, scripts, nodes (metadata only)
  - 📋 **Journey Service Enhancement**: Use ConnectionService for platform URLs and auth

## Next Steps - Implementation Plan

### ✅ Phase 0: Connection Foundations (COMPLETE)
**Built essential connection management - No more duplication**

**✅ Completed Components:**
1. **Connection Profile Management** (`pctl/core/conn/`)
   - Environment configs (URLs, service accounts, API keys)
   - Save/load connection profiles to `~/.pctl/connections.json`
   - Support multiple environments with validation

2. **Connection Service Layer** (`pctl/services/conn/`)
   - Business logic for profile CRUD operations
   - Config file loading (YAML) and validation
   - Cross-service communication via JSON/dict contracts

3. **Connection CLI Commands** (`pctl conn`)
   - `pctl conn add` - Dual input modes (flags vs config file)
   - `pctl conn list/show/delete` - Full profile management
   - Dynamic versioning from pyproject.toml

### ✅ Phase 1: Service Integration (COMPLETE)
**Token and Connection services fully integrated**

**✅ Completed Benefits:**
- ✅ Eliminated hardcoded platform URLs and credentials in TokenService
- ✅ Shared connection profiles across token and connection commands
- ✅ Consistent CLI pattern: `pctl <subcommand> <action> <conn_name>`
- ✅ Foundation for cross-service communication established

**✅ Completed Integration:**
1. **Token Service Integration** ✅
   - ✅ ConnectionService ↔ TokenService cross-service communication
   - ✅ Profile-based token generation: `pctl token get myenv`
   - ✅ Validation workflow: Only validated profiles can generate tokens
   - ✅ Clean service layer contracts with JSON/dict communication

2. **Connection Validation System** ✅
   - ✅ Automatic validation on profile creation (default behavior)
   - ✅ `--no-validate` flag for offline profile creation
   - ✅ Manual validation: `pctl conn validate myenv`
   - ✅ Interactive removal of invalid profiles
   - ✅ Validation status tracking in profile data

### ✅ Phase 2: HTTPClient Modernization (COMPLETE)
**Modern HTTP client with rich response objects and unified methods**

**✅ Completed Components:**
1. **HTTPClient Redesign** (`pctl/core/http_client.py`)
   - ✅ Rich HTTPResponse objects with status_code, headers, text, content access
   - ✅ New response methods: get_response(), post_response(), put_response(), delete_response()
   - ✅ Convenience methods: get_json(), post_json(), put_json(), delete_json()
   - ✅ Backward compatibility with existing .get(), .post() methods

2. **ELK Service Integration** (`pctl/services/elk/elk_service.py`)
   - ✅ Updated 8 critical locations to use new response methods
   - ✅ Fixed document count and index size calculation issues
   - ✅ Enhanced status display with connection profile information
   - ✅ All ELK commands tested and working with new HTTPClient

3. **Status Display Improvements** (`pctl/cli/elk.py`)
   - ✅ Changed "Environment" to "Streamer" for clarity
   - ✅ Added "Connection" column showing connection profiles
   - ✅ Fixed document counts and index sizes in status display

### ✅ Phase 3: Process Management Foundation (COMPLETE)
**Unified process management for CLI and Python processes**

**✅ Completed Components:**
1. **ProcessManager Development** (`pctl/core/process_manager.py`)
   - ✅ Built unified ProcessManager replacing subprocess_runner
   - ✅ Clean Python function interface - no argparse needed in worker modules
   - ✅ Uses `python -c` for direct function invocation
   - ✅ Two flows: background (start_background) and run-and-wait (run_and_wait)
   - ✅ Proper process detachment with os.setsid
   - ✅ Handle-based process control (ProcessHandle with PID)

2. **ELK Modernization** (`pctl/services/elk/`)
   - ✅ Removed deprecated subprocess_runner.py
   - ✅ Updated elk_service.py to use ProcessManager
   - ✅ Cleaned up log_streamer.py - removed argparse/main()
   - ✅ Worker just needs clean `run_streamer_process()` function
   - ✅ All ELK commands tested and working (init, start, stop, clean, purge, down)

### Phase 4: Advanced Features (FUTURE)
**Build on proven foundations**

1. **Log Analysis Commands**
   - `pctl log tail --profile myenv` - Real-time log viewing
   - `pctl log search --profile myenv [query]` - Historical search
   - Reuse connection profiles and API client

2. **Cross-Command Workflows**
   - Automatic token generation for journey testing
   - Seamless environment switching
   - Integrated debugging workflows

### Key Architecture Decisions
1. **Connection-first approach** - All services use shared profiles
   - Eliminates duplication and hardcoded configurations
   - Enables consistent cross-command environment management
   - Foundation for future API client patterns

2. **Incremental API client** - Build only when patterns emerge from integration
   - Avoid over-engineering by waiting for real usage patterns
   - Extract common API patterns after service integration
   - Focus on proven needs rather than speculative architecture

3. **Service layer contracts** - Clean JSON/dict communication between services
   - Services communicate via dictionaries for clean contracts
   - Hide async complexity in service layer, expose sync interfaces to CLI
   - Enable easy testing and cross-service integration

4. **Configuration flexibility** - Support both CLI flags and YAML configs
   - `pctl conn add` supports both `--flags` and `--config file.yaml`
   - Users choose their preferred workflow
   - Consistent patterns across all commands

## Log Subcommand Design

### Planned Commands

**Core Commands:**
- `pctl log tail [env]` - Real-time log tailing with smart filtering
- `pctl log search [env] [query]` - Search historical logs with date ranges
- `pctl log sources [env]` - List available log sources
- `pctl log filter [env] [--level] [--component]` - Advanced filtering

**Global Options:**
- `-e, --environment <env>` - PAIC environment [default: commkentsb2]
- `-s, --source <source>` - Log source [default: idm-everything]
- `-l, --level <level>` - Log level filter [default: ALL]
- `-v, --verbose` - Enable verbose logging
- `-n, --no-filter` - Disable noise filtering
- `--raw` - Raw JSON output (no pretty printing)

**Usage Examples:**
```bash
# Real-time log tailing (like frodo)
uv run pctl log tail

# Tail specific environment and source
uv run pctl log tail -e testenv -s am-authentication

# Search logs for errors in last 3 days
uv run pctl log search -e commkentsb2 --level ERROR --days 3

# Search for specific transaction ID
uv run pctl log search -e commkentsb2 --txid "abc123"

# Raw output for parsing
uv run pctl log tail --raw | jq '.payload.message'
```

### Implementation Strategy
1. **Start minimal** - Just tail and basic search
2. **Build on proven patterns** - Use existing HTTPClient and ConfigLoader
3. **Extract foundations when duplicated** - Don't over-engineer upfront
4. **Focus on operational needs** - Solve real debugging problems

## Log Subcommand Design

### Implemented Commands

**`pctl log search` - Historical log fetching and analysis**
```bash
pctl log search <conn_name> [options]
```

**Key Features:**
- ✅ Complete pagination (returns ALL logs, not just first page)
- ✅ Multi-day queries with automatic 24-hour window splitting
- ✅ Smart defaults (--days 1 by default, no time params needed)
- ✅ Server-side filtering via PAIC query filters
- ✅ Two output formats: JSONL (default, pipe-friendly) and JSON (with metadata)
- ✅ Configurable page size (1-1000, validated at both CLI and service layers)
- ✅ Rate limit handling with exponential backoff
- ✅ Service layer returns pure dicts (clean contracts, no model leakage)

**Options:**
- `-c, --component <source>` - Log source/component [default: idm-config]
- `--days <N>` - Search last N days [default: 1]
- `--from <date>` - Start time (YYYY-MM-DD or ISO-8601)
- `--to <date>` - End time (YYYY-MM-DD or ISO-8601)
- `-q, --query <filter>` - PAIC query filter expression
- `--txid <id>` - Transaction ID filter
- `-l, --log-level <1-4>` - Log level filter [default: 2]
- `--no-default-noise-filter` - Disable noise filtering
- `--page-size <N>` - Logs per page (1-1000) [default: 1000]
- `--max-pages <N>` - Max pages per window [default: 100]
- `--max-retries <N>` - Max retry attempts on 429 [default: 4]
- `-f, --format <jsonl|json>` - Output format [default: json]
- `-o, --output <file>` - Save to file (default: stdout)
- `-v, --verbose` - Enable verbose logging

**Examples:**
```bash
# Last 24h from idm-config (all defaults)
pctl log search myenv

# Last 7 days with filter (endpoint changes)
pctl log search myenv -c idm-config --days 7 -q '/payload/objectId co "endpoint/"'

# Specific date range
pctl log search myenv -c am-access --from 2025-10-01 --to 2025-10-06

# Save to file
pctl log search myenv -c idm-config --days 7 -o logs.jsonl

# Beautiful JSON for human reading
pctl log search myenv -c idm-config --format json -o report.json

# Pipe to jq for analysis
pctl log search myenv -c idm-config | jq '.payload.objectId'
```

**Performance:**
- ~2.7 seconds per 24-hour window (natural API throttling)
- 3-day search with filtering: ~8 seconds
- Tested with 3,210 logs (multi-page fetch)

**Use Cases:**
- Config change analysis (endpoint, journey, script modifications)
- Incident investigation (historical log search)
- Audit trail tracking (who changed what and when)
- Foundation for specialized analysis commands

**`pctl log changes` - Track configuration changes for endpoints/journeys/scripts**
```bash
pctl log changes <conn_name> --type <endpoint|journey|script> --name <resource_name> [options]
```

**Key Features:**
- ✅ Track CREATE/UPDATE/DELETE operations from PAIC audit logs
- ✅ Extract full audit trail: event_id, timestamp, operation, user_id, transaction_id
- ✅ Preserve JavaScript source code and globals configuration
- ✅ Three output formats: jsonl (compact), json (metadata), js (string arrays like Frodo)
- ✅ Resource type support: endpoint (tested), journey (ready), script (ready)
- ✅ Clean service layer architecture with ConfigChangeEvent models

**Options:**
- `--type <endpoint|journey|script>` - Resource type to track (required)
- `--name <resource_name>` - Resource name (required)
- `--days <N>` - Search last N days [default: 7]
- `--from <date>` - Start time (YYYY-MM-DD or ISO-8601)
- `--to <date>` - End time (YYYY-MM-DD or ISO-8601)
- `-f, --format <jsonl|json|js>` - Output format [default: json]
  - `jsonl` - Compact, one change per line
  - `json` - Beautiful JSON with metadata
  - `js` - Beautiful JSON with JavaScript as string arrays (like Frodo --use-string-arrays)
- `-o, --output <file>` - Save to file (default: stdout)
- `-v, --verbose` - Enable verbose logging

**Examples:**
```bash
# Last 7 days of endpoint changes (default format: json)
pctl log changes myenv --type endpoint --name my_endpoint

# Last 30 days, save to file
pctl log changes myenv --type endpoint --name my_endpoint --days 30 -o changes.json

# JavaScript source as string arrays (like Frodo)
pctl log changes myenv --type endpoint --name my_endpoint --format js -o changes.js

# Compact JSONL for piping
pctl log changes myenv --type endpoint --name my_endpoint --format jsonl | jq .

# Journey changes in specific date range
pctl log changes myenv --type journey --name Login --from 2025-09-01 --to 2025-10-01
```

**Output Structure:**
```json
{
  "success": true,
  "total_changes": 3,
  "resource_type": "endpoint",
  "resource_name": "my_endpoint",
  "time_range": {
    "start": "2025-09-07T04:22:23.949Z",
    "end": "2025-10-07T04:22:23.949Z",
    "requested_days": 30,
    "valid_days": 30,
    "skipped_days": 0
  },
  "changes": [
    {
      "event_id": "f6f7649d-...",
      "timestamp": "2025-10-03T03:59:02.240Z",
      "operation": "CREATE",
      "user_id": "2f12412b-...",
      "transaction_id": "frodo-ef2f07ed-...",
      "resource_type": "endpoint",
      "content": {
        "type": "text/javascript",
        "source": ["var UUID = java.util.UUID;", ...],  // String array when --format js
        "globals": ["{\n  \"request\": {...}", ...],
        "description": "",
        "resource_id": "endpoint/my_endpoint"
      }
    }
  ]
}
```

**Tested:**
- ✅ Endpoint changes (multiple environments tested)
- 📋 Journey changes (infrastructure ready, needs testing)
- 📋 Script changes (infrastructure ready, needs testing)

### Future Commands (Not Implemented)
- `pctl log analyze` - Journey performance analysis with statistics

## ELK Subcommand Design

### Command Structure

**Core Operations:**
- `pctl elk init` - Initialize ELK stack (containers + templates + policies)
- `pctl elk start [env]` - Start log streamer for environment [default: commkentsb2]
- `pctl elk stop [env]` - Stop log streamer for environment, if no env given: stop all
- `pctl elk status [env]` - Show streamer status for environment(s), if no env given: show all environments
- `pctl elk health` - Check ELK infrastructure health (containers, Elasticsearch, Kibana)

**Maintenance Operations:**
- `pctl elk clean <env>` - Clean old data (keep streamer running, clear index data) [env required]
- `pctl elk purge <env>` - Purge environment completely (stop streamer + delete indices) [env required]
- `pctl elk hardstop` - Stop all streamers and containers (safe - preserves data)
- `pctl elk down` - Stop all streamers and remove containers (deletes all data)

**Global Options:**
- `-l, --log-level <1-4>` - Set log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL) [default: 2]
- `-c, --component <comp>` - Set component(s) - comma separated [default: idm-core]
- `-F, --force` - Skip confirmation prompts (DANGEROUS)
- `-v, --verbose` - Enable verbose logging

### Connection Commands

**Available Commands:**
- `pctl conn add <name>` - Create new connection profile (dual input modes)
- `pctl conn list` - List all connection profiles
- `pctl conn show <name>` - Show profile details
- `pctl conn delete <name>` - Delete connection profile

**Options for `pctl conn add`:**
- `-c, --config PATH` - Path to YAML connection configuration file
- `--platform TEXT` - Platform URL (e.g. https://openam-env.id.forgerock.io)
- `--sa-id TEXT` - Service Account ID (required)
- `--sa-jwk-file PATH` - Path to Service Account JWK file
- `--sa-jwk TEXT` - Service Account JWK JSON string (alternative to file)
- `--log-api-key TEXT` - Log API key (optional)
- `--log-api-secret TEXT` - Log API secret (optional)
- `--admin-username TEXT` - Admin username (optional)
- `--admin-password TEXT` - Admin password (optional)
- `--description TEXT` - Profile description (optional)
- `-v, --verbose` - Enable verbose logging


### Journey Commands

**Available Commands:**
- `pctl journey run <config>` - Execute authentication journey from YAML config
- `pctl journey validate <config>` - Validate journey configuration syntax

**Options for `pctl journey run`:**
- `-s, --step` - Run in interactive step-by-step mode
- `-t, --timeout <ms>` - Request timeout in milliseconds (default: 30000)
- `-v, --verbose` - Enable verbose logging


## Foundation Building Philosophy

### **Incremental Foundation Approach**

We follow a **balanced approach** to building foundations - avoiding both over-engineering and technical debt.

#### **Build Foundations When:**
1. **Patterns emerge across 2+ commands** - Don't build speculatively
2. **Code duplication causes maintenance pain** - Extract when you feel it
3. **Adding new features becomes difficult** - Foundation gaps are blocking progress
4. **Consistency issues affect reliability** - Quality degradation is visible

#### **Don't Build Foundations When:**
- Only one command needs the functionality
- Patterns are still unclear or changing
- The "foundation" would be more complex than duplicated code
- Time pressure requires immediate problem-solving

### **Current Technical Debt & Improvements**

#### **🚧 ELK Subcommand Modernization (Priority: High)**
The ELK subcommand needs updates to match our foundation building philosophy:

1. **Upgrade to Official API:**
   - Replace Frodo subprocess with direct REST calls
   - Use same patterns as upcoming `pctl log` commands
   - Better error handling and performance

2. **Consistency Improvements:**
   - Replace direct `httpx` with shared `HTTPClient`
   - Remove unused imports (`json`, `yaml`)
   - Add missing `setup_logger` import

#### **🔧 Foundation Extraction Candidates**
*Build these only when patterns become clear:*

1. **PAIC API Client** - When log + ELK + future commands share API patterns
2. **Auth Manager** - When token management gets complex across commands
3. **Config Manager Enhancement** - If config loading patterns become complex
4. **Error Handling Patterns** - If exception handling needs become sophisticated

#### **✅ Healthy Foundation Examples**
- `HTTPClient` - Used by token & journey, will be used by log
- `ConfigLoader` - Shared YAML loading across all commands
- 3-layer architecture - Prevents tight coupling, enables testing

### **Refactoring Guidelines**
1. **Extract after 2nd duplication** - First duplication might be coincidence
2. **Keep extractions small and focused** - Don't build "kitchen sink" foundations
3. **Maintain backward compatibility** - Existing commands should keep working
4. **Test foundation changes thoroughly** - Shared code affects multiple commands

**Priority Order:**
1. **High**: ELK official API upgrade (blocks future log integration)
2. **Medium**: Code consistency improvements (quality of life)
3. **Low**: Speculative foundation building (wait for real needs)