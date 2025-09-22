"""
Token CLI commands - External interface layer
"""

import asyncio
import click

from ..services.token.token_service import TokenService
from ..core.logger import setup_logger

@click.group()
def token():
    """JWT token generation and management"""
    pass

@token.command()
@click.argument('conn_name')
@click.option('-f', '--format',
              type=click.Choice(['token', 'bearer', 'json']),
              default='token',
              help='Output format (default: token)')
@click.option('-v', '--verbose',
              is_flag=True,
              help='Enable verbose logging')
def get(conn_name: str, format: str, verbose: bool):
    """Generate PAIC Service Account access token from connection profile

    Usage:
      # Generate token from connection profile
      pctl token get myenv

      # Get token in different formats
      pctl token get myenv --format bearer
      pctl token get myenv --format json
    """

    # Setup logging based on verbose flag
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)

    # Run async token generation
    asyncio.run(_get_token_from_profile_async(conn_name, format, verbose))

async def _get_token_from_profile_async(conn_name: str, output_format: str, verbose: bool):
    """Async token generation from connection profile"""

    try:
        token_service = TokenService()

        if verbose:
            click.echo(f"Generating access token for connection profile: {conn_name}")

        # Get token from profile using service-to-service communication
        result = await token_service.get_token_from_profile(conn_name)

        if result["success"]:
            token = result["token"]

            # Format output according to requested format
            if output_format == "token":
                formatted_output = token
            elif output_format == "bearer":
                formatted_output = f"Bearer {token}"
            elif output_format == "json":
                import json
                formatted_output = json.dumps({
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": result.get("expires_in"),
                    "scope": result.get("scope")
                })

            # Always print as single line without Rich formatting for easy copy/paste
            print(formatted_output)

            if verbose:
                click.echo("✅ Token generated successfully")
                if result.get("expires_in"):
                    click.echo(f"   Expires in: {result['expires_in']} seconds")
                if result.get("scope"):
                    click.echo(f"   Scope: {result['scope']}")
        else:
            # Handle unvalidated profile error specially
            if result.get("unvalidated_profile"):
                click.echo(f"❌ {result['error']}", err=True)
                click.echo(f"   Use 'pctl conn validate {conn_name}' to validate the connection first.", err=True)
            else:
                click.echo(f"❌ Failed to generate token: {result['error']}", err=True)
            raise click.ClickException(result['error'])

    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        raise click.ClickException(f"Failed to generate token: {e}")

@token.command()
@click.argument('token_string')
def decode(token_string: str):
    """Decode and inspect JWT token (without verification)"""
    
    try:
        import jwt
        import json
        from datetime import datetime
        
        # Decode without verification to inspect contents
        decoded = jwt.decode(token_string, options={"verify_signature": False})
        
        # Format expiration time if present
        if 'exp' in decoded:
            exp_time = datetime.fromtimestamp(decoded['exp'])
            decoded['exp_formatted'] = exp_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Pretty print decoded token
        formatted_json = json.dumps(decoded, indent=2)
        
        click.echo("🔍 Decoded JWT Token")
        click.echo("=" * 50)
        click.echo(formatted_json)
        click.echo("=" * 50)
        
    except jwt.DecodeError as e:
        click.echo(f"❌ Invalid JWT format: {e}", err=True)
        raise click.ClickException("Invalid JWT token")
        
    except Exception as e:
        click.echo(f"❌ Failed to decode token: {e}", err=True)
        raise click.ClickException(str(e))

@token.command()  
@click.argument('token_string')
def validate(token_string: str):
    """Validate JWT token format and basic structure"""
    
    try:
        import jwt
        from datetime import datetime
        
        # Basic format validation (no signature verification)
        decoded = jwt.decode(token_string, options={"verify_signature": False})
        
        # Check basic JWT structure
        required_fields = ['iss', 'sub', 'aud', 'exp']
        missing_fields = [field for field in required_fields if field not in decoded]
        
        if missing_fields:
            click.echo(f"⚠️  Missing required JWT fields: {missing_fields}")
        
        # Check expiration
        if 'exp' in decoded:
            exp_time = datetime.fromtimestamp(decoded['exp'])
            current_time = datetime.now()
            
            if exp_time < current_time:
                click.echo("❌ Token has expired")
                click.echo(f"   Expired: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                time_left = exp_time - current_time
                click.echo("✅ Token is valid and not expired")
                click.echo(f"   Expires: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")
                click.echo(f"   Time left: {time_left}")
        
        click.echo("✅ JWT format is valid")
        
    except jwt.DecodeError as e:
        click.echo(f"❌ Invalid JWT format: {e}", err=True)
        raise click.ClickException("Invalid JWT token")
        
    except Exception as e:
        click.echo(f"❌ Validation error: {e}", err=True)
        raise click.ClickException(str(e))