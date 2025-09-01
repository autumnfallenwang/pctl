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
│   │   ├── token_service.py    # Token business logic
│   │   ├── journey_service.py  # Journey business logic
│   │   ├── elk_service.py      # ELK business logic
│   │   └── config_service.py   # Config management
│   ├── core/                   # ⚙️ Core Layer (Foundation)
│   │   ├── config.py           # Pydantic models
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
- `pctl elk start` → `ConfigService.load_config()`
- All commands → `ConfigService` for YAML parsing
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

- **Phase**: Token Implementation ✅
- **Complete**: 
  - Project setup with UV and 3-layer architecture
  - Token subcommand fully migrated from TypeScript
  - JWT creation and ForgeRock token exchange working
  - All output formats (token, bearer, json) functional
  - Decode and validate commands implemented
- **Next**: Journey subcommand migration
- **Ready**: Full token functionality with Rich CLI interface