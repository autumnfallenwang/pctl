"""
Connection CLI commands - External interface layer
"""

import json
from pathlib import Path
import click

from ..services.conn.conn_service import ConnectionService
from ..core.exceptions import ConfigError, ServiceError
from ..core.logger import setup_logger


@click.group()
def conn():
    """Connection profile management"""
    pass


@conn.command()
@click.argument('conn_name')
@click.option('--platform',
              help='Platform URL (e.g. https://openam-env.id.forgerock.io)')
@click.option('--sa-id',
              help='Service Account ID')
@click.option('--sa-jwk-file',
              type=click.Path(exists=True, path_type=Path),
              help='Path to Service Account JWK file')
@click.option('--sa-jwk',
              help='Service Account JWK JSON string (alternative to --sa-jwk-file)')
@click.option('--log-api-key',
              help='Log API key (optional)')
@click.option('--log-api-secret',
              help='Log API secret (optional)')
@click.option('--admin-username',
              help='Admin username (optional)')
@click.option('--admin-password',
              help='Admin password (optional)')
@click.option('--description',
              help='Profile description (optional)')
@click.option('-c', '--config', 'config_path',
              type=click.Path(exists=True, path_type=Path),
              help='Path to YAML connection configuration file')
@click.option('-v', '--verbose',
              is_flag=True,
              help='Enable verbose logging')
@click.option('--no-validate',
              is_flag=True,
              help='Do not validate connection credentials')
def add(conn_name: str, platform: str, sa_id: str, sa_jwk_file: Path, sa_jwk: str,
        log_api_key: str, log_api_secret: str, admin_username: str, admin_password: str,
        description: str, config_path: Path, verbose: bool, no_validate: bool):
    """Add a new connection profile

    Usage:
      # Using flags
      pctl conn add myenv --platform https://openam-env.id.forgerock.io --sa-id abc123 --sa-jwk-file /path/to/jwk.json

      # Using config file
      pctl conn add myenv --config /path/to/conn.yaml
    """

    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)

    try:
        connection_service = ConnectionService()

        # Determine validation setting
        validate = not no_validate

        # Determine input mode: config file vs flags
        if config_path:
            # Config file mode
            if verbose:
                click.echo(f"Loading connection profile from config: {config_path}")
                if not validate:
                    click.echo("⚠️  Skipping credential validation")

            result = connection_service.create_profile_from_config(config_path, conn_name, validate)

        else:
            # Flags mode
            if verbose:
                click.echo("Creating connection profile from command line arguments")
                if not validate:
                    click.echo("⚠️  Skipping credential validation")

            profile_data = _build_profile_from_flags(
                conn_name, platform, sa_id, sa_jwk_file, sa_jwk,
                log_api_key, log_api_secret, admin_username, admin_password, description
            )

            # Create the profile
            result = connection_service.create_profile(profile_data, validate)

        if result["success"]:
            click.echo(f"✅ {result['message']}")
            if verbose:
                click.echo(f"Profile saved for: {result['profile_name']}")
        else:
            click.echo(f"❌ Failed to create profile: {result['error']}", err=True)
            exit(1)

    except (ConfigError, ServiceError) as e:
        click.echo(f"❌ Error: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        exit(1)




def _build_profile_from_flags(conn_name: str, platform: str, sa_id: str,
                            sa_jwk_file: Path, sa_jwk: str,
                            log_api_key: str, log_api_secret: str,
                            admin_username: str, admin_password: str,
                            description: str) -> dict:
    """Build connection profile from command line flags"""

    # Validate required fields
    if not platform:
        raise click.UsageError("--platform is required when not using --config")
    if not sa_id:
        raise click.UsageError("--sa-id is required when not using --config")
    if not sa_jwk_file and not sa_jwk:
        raise click.UsageError("Either --sa-jwk-file or --sa-jwk is required when not using --config")
    if sa_jwk_file and sa_jwk:
        raise click.UsageError("Cannot specify both --sa-jwk-file and --sa-jwk")

    # Resolve JWK
    if sa_jwk_file:
        try:
            jwk_content = sa_jwk_file.read_text(encoding='utf-8')
            # Validate it's valid JSON
            json.loads(jwk_content)
            service_account_jwk = jwk_content
        except json.JSONDecodeError as e:
            raise click.UsageError(f"Invalid JSON in JWK file {sa_jwk_file}: {e}")
        except Exception as e:
            raise click.UsageError(f"Failed to read JWK file {sa_jwk_file}: {e}")
    else:
        try:
            # Validate JWK JSON string
            json.loads(sa_jwk)
            service_account_jwk = sa_jwk
        except json.JSONDecodeError as e:
            raise click.UsageError(f"Invalid JWK JSON string: {e}")

    # Build profile data
    profile_data = {
        "name": conn_name,
        "platform_url": platform,
        "service_account_id": sa_id,
        "service_account_jwk": service_account_jwk
    }

    # Add optional fields
    if log_api_key:
        profile_data["log_api_key"] = log_api_key
    if log_api_secret:
        profile_data["log_api_secret"] = log_api_secret
    if admin_username:
        profile_data["admin_username"] = admin_username
    if admin_password:
        profile_data["admin_password"] = admin_password
    if description:
        profile_data["description"] = description

    return profile_data


@conn.command()
@click.option('-v', '--verbose',
              is_flag=True,
              help='Enable verbose logging')
def list(verbose: bool):
    """List all connection profiles"""

    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)

    try:
        connection_service = ConnectionService()
        result = connection_service.list_profiles()

        if result["success"]:
            profiles = result["profiles"]

            if not profiles:
                click.echo("No connection profiles found.")
                return

            click.echo(f"Found {result['count']} connection profile(s):")
            click.echo()

            for profile in profiles:
                click.echo(f"📋 {profile['name']}")
                click.echo(f"   Platform: {profile['platform_url']}")
                click.echo(f"   Service Account: {profile['service_account_id']}")

                # Show optional fields
                if profile.get('description'):
                    click.echo(f"   Description: {profile['description']}")

                # Show available auth methods
                auth_methods = []
                if profile.get('log_api_key') and profile.get('log_api_secret'):
                    auth_methods.append("Log API")
                if profile.get('admin_username') and profile.get('admin_password'):
                    auth_methods.append("Admin")
                auth_methods.append("Service Account")  # Always available

                click.echo(f"   Auth methods: {', '.join(auth_methods)}")
                click.echo()
        else:
            click.echo(f"❌ Failed to list profiles: {result['error']}", err=True)
            exit(1)

    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        exit(1)


@conn.command()
@click.argument('conn_name')
@click.option('-v', '--verbose',
              is_flag=True,
              help='Enable verbose logging')
def show(conn_name: str, verbose: bool):
    """Show details of a specific connection profile"""

    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)

    try:
        connection_service = ConnectionService()
        result = connection_service.get_profile(conn_name)

        if result["success"]:
            profile = result["profile"]

            click.echo(f"📋 Connection Profile: {profile['name']}")
            click.echo(f"   Platform URL: {profile['platform_url']}")
            click.echo(f"   Service Account ID: {profile['service_account_id']}")

            if profile.get('description'):
                click.echo(f"   Description: {profile['description']}")

            click.echo(f"   Log API configured: {'✅' if profile.get('log_api_key') and profile.get('log_api_secret') else '❌'}")
            click.echo(f"   Admin credentials configured: {'✅' if profile.get('admin_username') and profile.get('admin_password') else '❌'}")
            click.echo(f"   Service Account configured: ✅")  # Always true for valid profiles
            click.echo(f"   Credentials validated: {'✅' if profile.get('validated', False) else '❌'}")

            if verbose:
                click.echo()
                click.echo("🔐 Service Account JWK (first 100 chars):")
                jwk_preview = profile['service_account_jwk'][:100] + "..." if len(profile['service_account_jwk']) > 100 else profile['service_account_jwk']
                click.echo(f"   {jwk_preview}")

        else:
            click.echo(f"❌ {result['error']}", err=True)
            exit(1)

    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        exit(1)


@conn.command()
@click.argument('conn_name')
@click.option('-v', '--verbose',
              is_flag=True,
              help='Enable verbose logging')
def validate(conn_name: str, verbose: bool):
    """Validate connection profile credentials"""

    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)

    try:
        connection_service = ConnectionService()

        if verbose:
            click.echo(f"Validating connection profile: {conn_name}")

        result = connection_service.validate_profile(conn_name)

        if result["success"]:
            if result.get("already_validated"):
                click.echo(f"✅ {result['message']}")
            else:
                click.echo(f"✅ {result['message']}")
                if verbose:
                    click.echo(f"Profile '{conn_name}' is now marked as validated")
        else:
            if result.get("validation_failed"):
                # Validation failed - ask user if they want to remove the profile
                click.echo(f"❌ {result['error']}")

                if click.confirm(f"Do you want to remove the invalid profile '{conn_name}'?"):
                    delete_result = connection_service.delete_profile(conn_name)
                    if delete_result["success"]:
                        click.echo(f"✅ {delete_result['message']}")
                    else:
                        click.echo(f"❌ Failed to delete profile: {delete_result['error']}", err=True)
                else:
                    click.echo(f"Profile '{conn_name}' kept but remains unvalidated")
            else:
                click.echo(f"❌ {result['error']}", err=True)
            exit(1)

    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        exit(1)


@conn.command()
@click.argument('conn_name')
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose',
              is_flag=True,
              help='Enable verbose logging')
def delete(conn_name: str, force: bool, verbose: bool):
    """Delete a connection profile"""

    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)

    try:
        if not force:
            if not click.confirm(f"Are you sure you want to delete profile '{conn_name}'?"):
                click.echo("Operation cancelled.")
                return

        connection_service = ConnectionService()
        result = connection_service.delete_profile(conn_name)

        if result["success"]:
            click.echo(f"✅ {result['message']}")
        else:
            click.echo(f"❌ {result['error']}", err=True)
            exit(1)

    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        exit(1)