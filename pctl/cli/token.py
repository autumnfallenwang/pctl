"""
Token CLI commands - External interface layer
"""

import asyncio
from pathlib import Path
import click

from ..services.token.token_service import TokenService
from ..core.token.token_models import TokenError
from ..core.exceptions import ConfigError
from ..core.logger import setup_logger

@click.group()
def token():
    """JWT token generation and management"""
    pass

@token.command()
@click.option('-c', '--config', 'config_path', 
              type=click.Path(exists=True, path_type=Path),
              required=True,
              help='Path to YAML token configuration file')
@click.option('-v', '--verbose', 
              is_flag=True,
              help='Enable verbose logging')
@click.option('-f', '--format',
              type=click.Choice(['token', 'bearer', 'json']),
              default='token',
              help='Output format (default: token)')
def get(config_path: Path, verbose: bool, format: str):
    """Generate PAIC Service Account access token from YAML config"""
    
    # Setup logging based on verbose flag
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)
    
    # Run async token generation
    asyncio.run(_get_token_async(config_path, verbose, format))

async def _get_token_async(config_path: Path, verbose: bool, output_format: str):
    """Async token generation implementation"""
    
    try:
        token_service = TokenService()
        
        if verbose:
            click.echo("Generating access token...")
        
        # Get token from service
        result = await token_service.get_token(config_path)
        
        # Format and output token
        formatted_output = token_service.format_token(result, output_format)
        
        # Always print as single line without Rich formatting for easy copy/paste
        print(formatted_output)
            
        if verbose:
            click.echo("✅ Token generated successfully")
            
    except ConfigError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        raise click.ClickException(str(e))
        
    except TokenError as e:
        click.echo(f"❌ Token error: {e}", err=True)
        raise click.ClickException(str(e))
        
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