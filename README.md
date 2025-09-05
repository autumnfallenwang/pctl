# pctl - PAIC Control CLI

Unified Python CLI for PAIC testing and development, combining token management, authentication flow testing, and local ELK stack management.

## Features

- **🔐 Token Management**: Generate, decode, and validate JWT tokens for PAIC services
- **🚀 Journey Testing**: End-to-end authentication flow testing
- **📊 ELK Management**: Local Elasticsearch + Kibana setup for log analysis with Frodo CLI integration

## Prerequisites

### Required Tools
- **Python 3.13+**
- **UV** (Python package manager)
- **Docker** and **Docker Compose**
- **Frodo CLI** (ForgeRock DevOps CLI)
- **curl**

### Supported Platforms
- **macOS** (Intel and Apple Silicon)
- **Linux** (Ubuntu/Debian, RHEL/CentOS/Fedora)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd pctl
   ```

2. **Install with UV:**

   **Option A: Global Installation (Recommended for users)**
   ```bash
   # Install pctl globally - run 'pctl' anywhere
   uv tool install .
   
   # Update your shell PATH (only needed if 'pctl' command not found after install)
   uv tool update-shell
   ```

   **Option B: Development Mode (Recommended for contributors)**
   ```bash
   # Install dependencies and create virtual environment
   uv sync
   
   # Use with 'uv run pctl' command
   ```

3. **Verify installation:**
   ```bash
   # For Global Installation (Option A)
   pctl --help
   pctl version
   pctl elk health
   
   # For Development Mode (Option B)
   uv run pctl --help
   uv run pctl version
   uv run pctl elk health
   
   # Run comprehensive verification script
   uv run python3 scripts/verify-install.py
   ```

## Quick Start

### Token Management
```bash
# Generate a service account token
pctl token get -c pctl/configs/token/examples/service-account.yaml
# (or: uv run pctl token get -c pctl/configs/token/examples/service-account.yaml)

# Decode a JWT token
pctl token decode "eyJ..."

# Validate token structure
pctl token validate "eyJ..."
```

### ELK Stack Management
```bash
# Initialize local ELK stack
pctl elk init

# Start log streaming for an environment
pctl elk start commkentsb2

# Check streamer status
pctl elk status

# Clean old data (keeps streamer running)
pctl elk clean commkentsb2

# Stop streamers
pctl elk stop
```

## Development

### Running Tests
```bash
uv run pytest
```

### Code Formatting
```bash
# Format code
uv run black .

# Lint code
uv run ruff check .
```

### Installing and Uninstalling
```bash
# Install globally for testing
uv tool install .

# Uninstall global installation
uv tool uninstall pctl
```

## Configuration

### Token Configuration
Configuration examples are provided in `pctl/configs/token/examples/`. Copy and modify these templates for your environment.

### ELK Configuration
The ELK stack is automatically configured with:
- **Elasticsearch**: Available at http://localhost:9200
- **Kibana**: Available at http://localhost:5601
- **Data Views**: Pre-configured for `paic-logs-*` pattern
- **Index Lifecycle**: 7-day retention with daily rollover

## Architecture

pctl follows a 3-layer architecture:
- **CLI Layer**: User interface (Click commands)
- **Service Layer**: Business logic and cross-command communication
- **Core Layer**: Shared utilities (HTTP, config, logging, platform detection)

## Installation Verification

The project includes a comprehensive verification script that checks all prerequisites:

```bash
# Run verification script
uv run python3 scripts/verify-install.py
```

This script will check:
- ✅ Python 3.13+ version
- ✅ UV package manager
- ✅ Docker and Docker Compose
- ✅ Docker daemon running
- ✅ curl availability
- ✅ Frodo CLI installation and version
- ✅ pctl project setup

## Troubleshooting

### Common Issues

**"Missing dependencies" error:**
```bash
# Check what's missing
pctl elk health

# Or run comprehensive verification
uv run python3 scripts/verify-install.py
```

## Support

For issues and feature requests, please visit the project repository.

## License

[Add your license information here]