"""
Journey CLI commands - External interface layer
"""

import asyncio
from pathlib import Path
import click

from ..services.journey.journey_service import JourneyService
from ..core.journey.journey_models import JourneyError
from ..core.exceptions import ConfigError
from ..core.logger import setup_logger


@click.group()
def journey():
    """Authentication journey testing commands"""
    pass


@journey.command()
@click.argument('file', 
               type=click.Path(exists=True, path_type=Path))
@click.option('--verbose', 
              is_flag=True,
              help='Enable verbose logging')
@click.option('-s', '--step', 
              is_flag=True,
              help='Run in interactive step-by-step mode')
@click.option('-t', '--timeout', 
              default='30000',
              help='Request timeout in milliseconds')
def run(file: Path, verbose: bool, step: bool, timeout: str):
    """Run an authentication journey using a YAML config file"""
    
    # Setup logging based on verbose flag
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)
    
    # Run async journey execution
    asyncio.run(_run_journey_async(file, verbose, step, int(timeout)))


@journey.command()
@click.argument('file', 
               type=click.Path(exists=True, path_type=Path))
@click.option('-v', '--verbose', 
              is_flag=True,
              help='Enable verbose logging')
def validate(file: Path, verbose: bool):
    """Validate a YAML configuration file"""
    
    # Setup logging based on verbose flag
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(log_level)
    
    # Run async validation
    asyncio.run(_validate_journey_async(file, verbose))


async def _run_journey_async(file: Path, verbose: bool, step_mode: bool, timeout: int):
    """Async journey execution implementation"""
    
    try:
        journey_service = JourneyService()
        
        # Load and validate config
        journey_config = await journey_service.load_config(file)
        
        # Execute journey
        result = await journey_service.run_journey(journey_config, step_mode, timeout)
        
        if result.success:
            click.echo("Journey completed successfully")
            if result.token_id:
                token_preview = result.token_id[:20] + "..." if len(result.token_id) > 20 else result.token_id
                click.echo(f"Token ID: {token_preview}")
            if result.success_url:
                click.echo(f"Success URL: {result.success_url}")
        else:
            click.echo(f"Journey failed: {result.error}", err=True)
            exit(1)
        
    except (JourneyError, ConfigError) as e:
        click.echo(f"Command failed: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"Command failed: {e}", err=True)
        exit(1)


async def _validate_journey_async(file: Path, verbose: bool):
    """Async journey validation implementation"""
    
    try:
        journey_service = JourneyService()
        
        # Load and validate config
        journey_config = await journey_service.load_config(file)
        
        click.echo("Configuration is valid!")
        click.echo(f"Journey: {journey_config.journey_name}")
        click.echo(f"Platform: {journey_config.platform_url}")
        click.echo(f"Realm: {journey_config.realm}")
        click.echo(f"Steps: {len(journey_config.steps)}")
        
    except (JourneyError, ConfigError) as e:
        click.echo(f"Command failed: {e}", err=True)
        exit(1)
    except Exception as e:
        click.echo(f"Command failed: {e}", err=True)
        exit(1)