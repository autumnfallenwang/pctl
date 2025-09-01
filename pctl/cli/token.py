"""
Token CLI commands - External interface layer
"""

import asyncio
from pathlib import Path
import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..services.token_service import TokenService
from ..core.exceptions import TokenError, ConfigError
from ..core.logger import setup_logger

console = Console()

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
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            
            # Show progress for token generation  
            task = progress.add_task("Generating access token...", total=100)
            
            # Get token from service
            result = await token_service.get_token(config_path)
            progress.update(task, completed=100)
        
        # Format and output token
        formatted_output = token_service.format_token(result, output_format)
        
        # Always print as single line without Rich formatting for easy copy/paste
        print(formatted_output)
            
        if verbose:
            console.print(f"✅ Token generated successfully", style="green")
            
    except ConfigError as e:
        console.print(f"❌ Configuration error: {e}", style="red") 
        raise click.ClickException(str(e))
        
    except TokenError as e:
        console.print(f"❌ Token error: {e}", style="red")
        raise click.ClickException(str(e))
        
    except Exception as e:
        console.print(f"❌ Unexpected error: {e}", style="red")
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
        
        console.print(Panel(
            formatted_json,
            title="🔍 Decoded JWT Token",
            border_style="blue"
        ))
        
    except jwt.DecodeError as e:
        console.print(f"❌ Invalid JWT format: {e}", style="red")
        raise click.ClickException("Invalid JWT token")
        
    except Exception as e:
        console.print(f"❌ Failed to decode token: {e}", style="red")
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
            console.print(f"⚠️  Missing required JWT fields: {missing_fields}", style="yellow")
        
        # Check expiration
        if 'exp' in decoded:
            exp_time = datetime.fromtimestamp(decoded['exp'])
            current_time = datetime.now()
            
            if exp_time < current_time:
                console.print("❌ Token has expired", style="red")
                console.print(f"   Expired: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                time_left = exp_time - current_time
                console.print("✅ Token is valid and not expired", style="green")
                console.print(f"   Expires: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")
                console.print(f"   Time left: {time_left}")
        
        console.print("✅ JWT format is valid", style="green")
        
    except jwt.DecodeError as e:
        console.print(f"❌ Invalid JWT format: {e}", style="red")
        raise click.ClickException("Invalid JWT token")
        
    except Exception as e:
        console.print(f"❌ Validation error: {e}", style="red") 
        raise click.ClickException(str(e))