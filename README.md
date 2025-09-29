# pctl - PAIC Control CLI

**Version 0.5.1**

Unified Python CLI for PAIC (PingOne Advanced Identity Cloud) operational tooling - debugging, testing, analysis, and problem-solving.

## Features

- **🔐 Token Management**: Profile-based JWT token generation with validation workflow
- **🚀 Journey Testing**: End-to-end authentication flow testing with step-by-step mode
- **📊 ELK Management**: Local Elasticsearch + Kibana setup for log analysis with enhanced status display
- **🔗 Connection Profiles**: Centralized credential and environment management with validation
- **🛡️ Credential Validation**: Automatic and manual validation of connection credentials
- **⚡ Consistent CLI Pattern**: `pctl <subcommand> <action> <conn_name>` across all commands
- **🌐 Modern HTTP Client**: Rich response objects with status codes, headers, and unified request methods

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
# Create connection profile using flags (validates by default)
pctl conn add myenv \
  --platform https://openam-myenv.id.forgerock.io \
  --sa-id "your-service-account-id" \
  --sa-jwk-file /path/to/service-account.jwk

# Create from config file
pctl conn add myenv --config /path/to/connection-config.yaml

# Create without validation (for offline setup)
pctl conn add myenv --config /path/to/connection-config.yaml --no-validate

# Manually validate a connection profile
pctl conn validate myenv

# List all profiles
pctl conn list

# Show profile details (includes validation status)
pctl conn show myenv

# Delete profile
pctl conn delete myenv
```

### Token Management
```bash
# Generate token from connection profile
pctl token get myenv

# Get token in different formats
pctl token get myenv --format bearer
pctl token get myenv --format json

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
# Initialize local ELK stack (containers + templates + policies)
pctl elk init

# Start log streaming (streamer name defaults to connection profile name)
pctl elk start myenv

# Start with custom settings and streamer name
pctl elk start myenv --name my-streamer --log-level 3 --component idm-core,am-authentication

# Check status of all streamers (shows connection profiles and document counts)
pctl elk status

# Check specific streamer status
pctl elk status --name my-streamer

# Check ELK infrastructure health
pctl elk health

# Clean old data for specific streamer (keeps streamer running)
pctl elk clean --name my-streamer

# Stop specific streamer
pctl elk stop --name my-streamer

# Stop all streamers
pctl elk stop

# Purge streamer completely (stop + delete all data)
pctl elk purge --name my-streamer

# Stop all streamers and containers (preserves data)
pctl elk hardstop

# Remove everything (deletes all data)
pctl elk down
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

### Connection Profile Validation

pctl includes a comprehensive validation system for connection profiles:

- **Automatic validation** during profile creation (default)
- **Manual validation** for profiles created with `--no-validate`
- **Validation status tracking** in profile data
- **Token generation protection** - only validated profiles can generate tokens

```bash
# Profiles are validated automatically by default
pctl conn add myenv --config connection.yaml  # validates credentials

# Skip validation for offline setup
pctl conn add myenv --config connection.yaml --no-validate

# Manually validate later
pctl conn validate myenv  # tests credentials and marks as validated

# Token generation requires validated profiles
pctl token get myenv  # only works with validated profiles
```

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