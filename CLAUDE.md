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

- **Phase**: Project Setup ✅
- **Next**: Migrate token subcommand from authflow TypeScript
- **Ready**: Basic CLI structure with 3-layer architecture complete