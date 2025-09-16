# pctl - PAIC Control CLI

**Version 0.3.0**

Unified Python CLI for PAIC (PingOne Advanced Identity Cloud) operational tooling - debugging, testing, analysis, and problem-solving.

## Features

- **🔐 Token Management**: Generate, decode, and validate JWT tokens for PAIC services
- **🚀 Journey Testing**: End-to-end authentication flow testing with step-by-step mode
- **📊 ELK Management**: Local Elasticsearch + Kibana setup for log analysis
- **🔗 Connection Profiles**: Centralized credential and environment management
- **⚡ Dual Input Modes**: Use CLI flags or YAML configuration files

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
   
   # Update global installation with latest code changes (most reliable)
   uv tool uninstall pctl && uv clean && uv tool install . --reinstall
   
   # Update your shell PATH (only needed if 'pctl' command not found after install)
   uv tool update-shell
   ```

   **Option B: Development Mode (Recommended for contributors)**
   ```bash
   # Install dependencies and create virtual environment
   uv sync
   
   # Use with 'uv run pctl' command (always uses latest code)
   # No need to reinstall - code changes are immediately available
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

### Connection Management

First, set up connection profiles for your PAIC environments:

```bash
# Create connection profile using flags
pctl conn add myenv \
  --platform https://openam-myenv.id.forgerock.io \
  --sa-id "your-service-account-id" \
  --sa-jwk-file /path/to/service-account.jwk

# Or create from config file
pctl conn add myenv --config /path/to/connection-config.yaml

# List all profiles
pctl conn list

# Show profile details
pctl conn show myenv

# Delete profile
pctl conn delete myenv
```

### Token Management
```bash
# Generate a service account token
pctl token get -c pctl/configs/token/examples/service-account.yaml

# Decode a JWT token
pctl token decode "eyJ..."

# Validate token structure
pctl token validate "eyJ..."
```

### Journey Testing
```bash
# Run authentication journey from config
pctl journey run pctl/configs/journey/examples/basic-login.yaml

# Run in interactive step-by-step mode
pctl journey run pctl/configs/journey/examples/basic-login.yaml --step

# Validate journey configuration
pctl journey validate pctl/configs/journey/examples/basic-login.yaml
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

### Uninstalling
```bash
# Uninstall global installation
uv tool uninstall pctl
```

## Configuration

### Connection Profiles

Connection profiles store environment credentials and configuration:

```yaml
# Example: pctl/configs/conn/examples/connection.yaml
platform: "https://openam-env.id.forgerock.io"
sa_id: "service-account-id"
sa_jwk: '{"kty":"RSA","kid":"example",...}'  # Direct JSON string
# OR
sa_jwk_file: "/path/to/jwk.json"  # File path (relative to config file)
log_api_key: "optional-log-key"
log_api_secret: "optional-log-secret"
admin_username: "optional-admin"
admin_password: "optional-password"
description: "Environment description"
```

### Token Configuration
Configuration examples are provided in `pctl/configs/token/examples/`. Copy and modify these templates for your environment.

### Journey Configuration
Configuration examples are provided in `pctl/configs/journey/examples/`. Copy and modify these templates for your authentication flows.

### ELK Configuration
The ELK stack is automatically configured with:
- **Elasticsearch**: Available at http://localhost:9200
- **Kibana**: Available at http://localhost:5601
- **Data Views**: Pre-configured for `paic-logs-*` pattern
- **Index Lifecycle**: 7-day retention with daily rollover

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