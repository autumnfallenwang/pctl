# pctl - PAIC Control CLI

> **This is the single source of truth for the current implementation plan and status, with high level guide.**

## Current Implementation Plan

**Unified Python CLI** merging authflow (TS) + plctl.sh (Bash) into `pctl` with three subcommands:
- `pctl token` - JWT/access token management
- `pctl journey` - Authentication flow testing  
- `pctl elk` - Local ELK stack management

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
- CLI commands → Service layer only
- Services → Core utilities only  
- Cross-command calls → Service layer only
- No CLI → Core direct calls
- No Service → CLI calls

## Project Structure

```
pctl/
├── pyproject.toml
├── pctl/
│   ├── cli/                    # 🖥️ CLI Layer
│   │   ├── main.py             # Click entry point
│   │   ├── token.py            # Token commands
│   │   ├── journey.py          # Journey commands
│   │   └── elk.py              # ELK commands
│   ├── services/               # 🔄 Service Layer (Internal API)
│   │   ├── token/              # Token business logic
│   │   ├── journey/            # Journey business logic
│   │   └── elk/                # ELK business logic
│   ├── core/                   # ⚙️ Core Layer (Foundation)
│   │   ├── config.py           # Configuration loading utilities
│   │   ├── token/              # Token-specific models and utilities
│   │   ├── elk/                # ELK-specific models and utilities
│   │   ├── http_client.py      # HTTP utilities
│   │   ├── subprocess_runner.py # Process execution
│   │   ├── logger.py           # Logging setup
│   │   └── exceptions.py       # Custom exceptions
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
uv run pctl token --help

# Run with development dependencies 
uv sync
```

### Token Commands

**Available Commands:**
- `pctl token get` - Generate PAIC Service Account access token from YAML config
- `pctl token decode` - Decode and inspect JWT token (without verification)  
- `pctl token validate` - Validate JWT token format and basic structure

**Options for `pctl token get`:**
- `-c, --config PATH` - Path to YAML token configuration file (required)
- `-v, --verbose` - Enable verbose logging
- `-f, --format [token|bearer|json]` - Output format (default: token)

**Examples:**
```bash
# Basic token generation (token format)
uv run pctl token get -c pctl/configs/token/real/service-account.yaml

# Generate with verbose logging
uv run pctl token get -c pctl/configs/token/real/service-account.yaml -v

# Generate in bearer format
uv run pctl token get -c pctl/configs/token/real/service-account.yaml -f bearer

# Generate in JSON format with verbose logging
uv run pctl token get -c pctl/configs/token/real/service-account.yaml -f json -v

# Decode JWT token (inspect payload)
uv run pctl token decode "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZXN0IjoicGF5bG9hZCJ9..."

# Validate JWT token structure and expiration
uv run pctl token validate "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZXN0IjoicGF5bG9hZCJ9..."

# Use example config (will fail - demo purposes)
uv run pctl token get -c pctl/configs/token/examples/service-account.yaml -v
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

- **Phase**: Journey Implementation 🚧
- **Complete**: 
  - Project setup with UV and 3-layer architecture
  - Token subcommand fully migrated from TypeScript (✅ COMPLETE)
    - JWT creation and ForgeRock token exchange working
    - All output formats (token, bearer, json) functional
    - Decode and validate commands implemented
  - ELK stack management fully implemented (✅ COMPLETE)
    - Complete ELK stack management with 9 commands
    - Real-time log streaming from Frodo to Elasticsearch
    - Registry-based streamer management with process tracking
    - Cross-platform support (Linux x64, Mac ARM)
    - Clean Python distribution without build complexity
- **Current**: Journey subcommand implementation 
- **Legacy Reference**: TypeScript authflow journey implementation available in `examples/authflow/`

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

### Usage Examples

```bash
# Initialize ELK stack
uv run pctl elk init

# Start streamer for default environment  
uv run pctl elk start

# Start streamer for specific environment
uv run pctl elk start testenv

# Check status of all environments
uv run pctl elk status

# Check ELK infrastructure health
uv run pctl elk health

# Stop all streamers
uv run pctl elk stop

# Clean data for specific environment
uv run pctl elk clean testenv

# Stop everything safely (preserves data)
uv run pctl elk hardstop

# Remove everything (deletes all data)
uv run pctl elk down
```

## Journey Subcommand Implementation Plan

### Legacy Reference Analysis
The TypeScript authflow implementation in `examples/authflow/` provides comprehensive journey functionality:

**Key Features from Legacy Implementation:**
- Journey initialization and step-by-step execution
- Interactive and automated modes
- YAML-based configuration with step definitions
- Callback processing and response handling
- Token extraction and success URL capture
- Comprehensive error handling and logging

### Journey Implementation Todos

**Phase 1: Foundation (Current)**
- [ ] Create `pctl/cli/journey.py` - Journey CLI commands
- [ ] Create `pctl/services/journey/` - Journey service layer
- [ ] Create `pctl/core/journey/` - Journey models and utilities
- [ ] Add journey config support in `pctl/configs/journey/`

**Phase 2: Core Implementation**
- [ ] Implement `JourneyConfig` model (from legacy `JourneyConfig` interface)
- [ ] Implement `JourneyService` with HTTP client integration
- [ ] Create callback processing logic
- [ ] Add step-by-step execution engine
- [ ] Implement response parsing and token extraction

**Phase 3: CLI Integration**  
- [ ] Add `pctl journey run <config>` command
- [ ] Add `pctl journey validate <config>` command
- [ ] Add `pctl journey list` command (list available configs)
- [ ] Support interactive (`--step`) and automated modes
- [ ] Add verbose logging and progress indicators

**Phase 4: Advanced Features**
- [ ] Integration with TokenService for authenticated journeys
- [ ] Journey templates and config generation
- [ ] Journey debugging and troubleshooting tools
- [ ] Performance metrics and timing analysis

### Journey Command Structure

**Core Commands:**
- `pctl journey run <config>` - Execute authentication journey from YAML config
- `pctl journey validate <config>` - Validate journey configuration syntax
- `pctl journey list` - List available journey configurations
- `pctl journey template <name>` - Generate journey config template

**Options:**
- `-s, --step` - Run in interactive step-by-step mode
- `-t, --timeout <ms>` - Request timeout in milliseconds
- `-v, --verbose` - Enable verbose logging
- `--dry-run` - Validate config without executing journey

**Usage Examples:**
```bash
# Run journey from config
uv run pctl journey run pctl/configs/journey/real/login-flow.yaml

# Run in interactive step mode
uv run pctl journey run pctl/configs/journey/real/login-flow.yaml --step

# Validate journey config
uv run pctl journey validate pctl/configs/journey/examples/basic-login.yaml

# List available journey configs
uv run pctl journey list

# Generate template config
uv run pctl journey template basic-auth > my-journey.yaml
```

### Journey Config Format (YAML)
```yaml
# Journey configuration based on legacy authflow format
platform_url: "https://your-forgerock-platform.com"
realm: "alpha"  
journey_name: "Login"
timeout_ms: 30000

# Step definitions with callback responses
steps:
  username:
    prompt: "User Name"
    value: "demo"
  password:
    prompt: "Password" 
    value: "changeit"
  
# Optional settings
interactive: false
verbose: true
extract_token: true
follow_redirects: true
```