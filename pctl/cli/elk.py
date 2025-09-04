"""
ELK CLI Commands - Local ELK stack management
"""

import asyncio
from pathlib import Path
from typing import Optional

import click

from ..services.elk.elk_service import ELKService
from ..core.elk.elk_models import ELKConfig, HealthStatus
from ..core.exceptions import ELKError


@click.group()
@click.option("--config-dir", type=click.Path(exists=True, file_okay=False, dir_okay=True), 
              help="Configuration directory (default: ./configs relative to pctl binary)")
@click.pass_context
def elk(ctx, config_dir):
    """🐳 Local ELK stack management"""
    ctx.ensure_object(dict)
    ctx.obj['config_dir'] = config_dir


@elk.command()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
async def init(ctx, verbose: bool):
    """Initialize ELK stack (containers + templates + policies)"""
    
    config_dir = ctx.obj.get('config_dir')
    try:
        service = ELKService(config_dir=config_dir)
    except FileNotFoundError as e:
        if "No such file or directory" in str(e):
            click.echo("❌ Config directory setup failed", err=True)
            click.echo("   Use one of the solutions shown above, then try again.")
            raise click.Abort()
        else:
            raise
    
    try:
        # Check current health
        if verbose:
            click.echo("Checking ELK health...")
        health = await service.check_health()
        
        if health.overall_status == HealthStatus.HEALTHY:
            click.echo("✅ ELK stack already running and healthy")
            _display_health_status(health, verbose)
            return
        
        # Initialize stack
        click.echo("Initializing ELK stack...")
        await service.init_stack()
        click.echo("✅ ELK stack initialized")
        
        # Display final status
        health = await service.check_health()
        _display_health_status(health, verbose)
        
        click.echo()
        click.echo("🎉 ELK stack ready!")
        click.echo("   📊 Elasticsearch: http://localhost:9200")
        click.echo("   📈 Kibana: http://localhost:5601")
        
    except ELKError as e:
        click.echo(f"❌ Failed to initialize ELK stack: {e}", err=True)
        raise click.Abort()


@elk.command()
@click.argument("environment", required=False, default="commkentsb2")
@click.option("-l", "--log-level", type=click.IntRange(1, 4), default=2, 
              help="Log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL)")
@click.option("-c", "--component", default="idm-core", 
              help="Log component(s) - comma separated")
@click.option("--log-dir", type=click.Path(exists=True, file_okay=False, dir_okay=True), 
              help="Directory for log and PID files (default: current directory)")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
async def start(ctx, environment: str, log_level: int, component: str, log_dir: Optional[str], verbose: bool):
    """Start log streamer for environment [default: commkentsb2]"""
    
    config_dir = ctx.obj.get('config_dir')
    try:
        service = ELKService(config_dir=config_dir)
    except FileNotFoundError as e:
        if "No such file or directory" in str(e):
            click.echo("❌ Config directory setup failed", err=True)
            click.echo("   Use one of the solutions shown above, then try again.", err=True)
            raise click.Abort()
        else:
            raise
    config = ELKConfig(
        log_level=log_level,
        component=component,
        verbose=verbose
    )
    
    try:
        # Auto-initialization check
        click.echo("Checking ELK infrastructure...")
        health = await service.check_health()
        
        if health.overall_status == HealthStatus.NOT_FOUND:
            click.echo("Infrastructure not found, initializing...")
            await service.init_stack()
            health = await service.check_health()
        elif health.overall_status == HealthStatus.STOPPED:
            click.echo("Starting ELK containers...")
            # TODO: Add start_containers method
            await asyncio.sleep(2)  # Placeholder
            health = await service.check_health()
        
        if health.overall_status != HealthStatus.HEALTHY:
            raise ELKError(f"ELK infrastructure is {health.overall_status.value}")
        
        # Start streamer
        click.echo(f"Starting streamer for {environment}...")
        log_dir_path = Path(log_dir) if log_dir else None
        process_info = await service.start_streamer(environment, config, log_dir_path)
        
        # Display status
        click.echo(f"\\n🚀 Streamer started for {environment}")
        click.echo(f"   📊 PID: {process_info.pid}")
        click.echo(f"   📝 Logs: {process_info.log_file}")
        click.echo(f"   🔧 Component: {component}")
        click.echo(f"   📈 Log Level: {log_level}")
        
    except ELKError as e:
        click.echo(f"❌ Failed to start streamer: {e}", err=True)
        raise click.Abort()


@elk.command()
@click.argument("environment", required=False)
async def stop(environment: Optional[str]):
    """Stop log streamer for environment, if no env given: stop all"""
    
    # Stop only needs PID files, not config
    service = ELKService(require_config=False)
    
    try:
        if environment:
            # Stop specific environment
            click.echo(f"Stopping streamer for {environment}...")
            success = await service.stop_streamer(environment)
            
            if success:
                click.echo(f"✅ Stopped streamer for {environment}")
            else:
                click.echo(f"⚠️  Streamer for {environment} was not running")
        else:
            # Stop all streamers
            click.echo("Stopping all streamers...")
            stopped_count = await service.stop_all_streamers()
            
            if stopped_count > 0:
                click.echo(f"✅ Stopped {stopped_count} streamer(s)")
            else:
                click.echo("ℹ️  No streamers were running")
            
    except ELKError as e:
        click.echo(f"❌ Failed to stop streamer(s): {e}", err=True)
        raise click.Abort()


@elk.command()
@click.argument("environment", required=False)
async def status(environment: Optional[str]):
    """Show streamer status for environment(s), if no env given: show all"""
    
    # Status only needs PID files and HTTP checks, not config
    service = ELKService(require_config=False)
    
    try:
        if environment:
            # Show specific environment
            click.echo(f"Getting status for {environment}...")
            status = await service.get_status(environment)
            _display_single_status(status)
        else:
            # Show all environments  
            click.echo("Getting status for all environments...")
            statuses = await service.get_all_statuses()
            
            if not statuses:
                click.echo("ℹ️  No streamers found")
                return
            
            _display_multiple_statuses(statuses)
            
    except ELKError as e:
        click.echo(f"❌ Failed to get status: {e}", err=True)
        raise click.Abort()


@elk.command()
async def health():
    """Check ELK infrastructure health (containers, Elasticsearch, Kibana)"""
    
    # Health check doesn't need config files
    service = ELKService(require_config=False)
    
    try:
        click.echo("Checking ELK health...")
        health = await service.check_health()
        click.echo("✅ Health check complete")
        
        _display_health_status(health)
        
    except ELKError as e:
        click.echo(f"❌ Health check failed: {e}", err=True)
        raise click.Abort()


@elk.command()
@click.argument("environment", required=True)
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts")
@click.pass_context
async def clean(ctx, environment: str, force: bool):
    """Clean old data (keep streamer running, clear index data) [env required]"""
    
    if not force:
        if not click.confirm(f"⚠️  Clean all data for {environment}? This will delete Elasticsearch indices."):
            click.echo("Cancelled.")
            return
    
    # Clean only needs Elasticsearch connection, not config files
    service = ELKService(require_config=False)
    
    try:
        click.echo(f"Cleaning data for {environment}...")
        await service.clean_environment_data(environment)
        
        click.echo(f"🧹 Cleaned data for {environment}")
        
    except ELKError as e:
        click.echo(f"❌ Failed to clean data: {e}", err=True)
        raise click.Abort()


@elk.command()
@click.argument("environment", required=True)
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts")
@click.pass_context
async def purge(ctx, environment: str, force: bool):
    """Purge environment completely (stop streamer + delete indices) [env required]"""
    
    if not force:
        if not click.confirm(f"💥 Purge environment {environment} completely? This will stop streamer and delete all data."):
            click.echo("Cancelled.")
            return
    
    # Purge only needs PID files and Elasticsearch connection, not config files
    service = ELKService(require_config=False)
    
    try:
        click.echo(f"Purging environment {environment}...")
        await service.purge_environment(environment)
        
        click.echo(f"💥 Purged environment {environment} completely")
        
    except ELKError as e:
        click.echo(f"❌ Failed to purge environment: {e}", err=True)
        raise click.Abort()


@elk.command()
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts")
@click.pass_context
async def hardstop(ctx, force: bool):
    """Stop all streamers and containers (safe - preserves data)"""
    
    if not force:
        if not click.confirm("🛑 Stop all streamers and ELK containers? Data will be preserved."):
            click.echo("Cancelled.")
            return
    
    config_dir = ctx.obj.get('config_dir')
    try:
        service = ELKService(config_dir=config_dir)
    except FileNotFoundError as e:
        if "No such file or directory" in str(e):
            click.echo("❌ Config directory setup failed", err=True)
            click.echo("   Use one of the solutions shown above, then try again.", err=True)
            raise click.Abort()
        else:
            raise
    
    try:
        # Stop all streamers first
        click.echo("Stopping all streamers...")
        stopped_count = await service.stop_all_streamers()
        
        # Stop containers
        click.echo("Stopping ELK containers...")
        await service.stop_containers()
        
        click.echo(f"🛑 Stopped {stopped_count} streamer(s) and ELK containers")
        
    except ELKError as e:
        click.echo(f"❌ Failed to stop ELK stack: {e}", err=True)
        raise click.Abort()


@elk.command()
@click.option("-F", "--force", is_flag=True, help="Skip confirmation prompts")
@click.pass_context
async def down(ctx, force: bool):
    """Stop all streamers and remove containers (deletes all data)"""
    
    if not force:
        if not click.confirm("💥 Remove all streamers and ELK containers? ALL DATA WILL BE DELETED."):
            click.echo("Cancelled.")
            return
    
    config_dir = ctx.obj.get('config_dir')
    try:
        service = ELKService(config_dir=config_dir)
    except FileNotFoundError as e:
        if "No such file or directory" in str(e):
            click.echo("❌ Config directory setup failed", err=True)
            click.echo("   Use one of the solutions shown above, then try again.", err=True)
            raise click.Abort()
        else:
            raise
    
    try:
        # Stop all streamers first
        click.echo("Stopping all streamers...")
        stopped_count = await service.stop_all_streamers()
        
        # Remove containers and volumes
        click.echo("Removing ELK containers and volumes...")
        await service.remove_containers()
        
        click.echo(f"💥 Removed {stopped_count} streamer(s) and all ELK data")
        
    except ELKError as e:
        click.echo(f"❌ Failed to remove ELK stack: {e}", err=True)
        raise click.Abort()



# Helper functions for plain text display

def _display_health_status(health, verbose: bool = False) -> None:
    """Display ELK health status in plain text"""
    
    if not verbose:
        return
        
    click.echo(f"ELK Health: {health.overall_status.value.upper()}")
    click.echo("=" * 40)
    click.echo(f"Platform:           {health.platform_name}")
    click.echo(f"Containers Exist:   {'✅' if health.containers_exist else '❌'}")
    click.echo(f"Containers Running: {'✅' if health.containers_running else '❌'}")
    click.echo(f"Elasticsearch:      {'✅ ' + health.elasticsearch_version if health.elasticsearch_healthy else '❌'}")
    click.echo(f"Kibana:             {'✅' if health.kibana_available else '❌'}")
    click.echo("=" * 40)


def _display_single_status(status) -> None:
    """Display single environment status"""
    
    state = "RUNNING" if status.process_running else "STOPPED"
    
    click.echo(f"\\nStreamer Status: {state}")
    click.echo("=" * 40)
    click.echo(f"Environment:        {status.environment}")
    click.echo(f"Process Running:    {'✅' if status.process_running else '❌'}")
    if status.pid:
        click.echo(f"PID:                {status.pid}")
    if status.log_file_path:
        click.echo(f"Log File:           {status.log_file_path}")
    if status.log_file_size:
        click.echo(f"Log Size:           {status.log_file_size}")
    if status.index_doc_count is not None:
        click.echo(f"Documents:          {status.index_doc_count:,}")
    if status.index_size:
        click.echo(f"Index Size:         {status.index_size}")
    click.echo("=" * 40)


def _display_multiple_statuses(statuses) -> None:
    """Display multiple environment statuses in a table"""
    
    click.echo("\\nEnvironment Status:")
    click.echo("=" * 80)
    
    # Table header
    header = f"{'Environment':<15} {'Status':<12} {'PID':<8} {'Documents':<12} {'Index Size':<12} {'Log Size':<12}"
    click.echo(header)
    click.echo("-" * 80)
    
    for status in statuses:
        status_icon = "✅ Running" if status.process_running else "❌ Stopped"
        pid = str(status.pid) if status.pid else "-"
        doc_count = f"{status.index_doc_count:,}" if status.index_doc_count is not None else "-"
        index_size = status.index_size or "-"
        log_size = status.log_file_size or "-"
        
        row = f"{status.environment:<15} {status_icon:<12} {pid:<8} {doc_count:<12} {index_size:<12} {log_size:<12}"
        click.echo(row)
    
    click.echo("=" * 80)
    click.echo()


# Async command wrapper
def async_command(f):
    """Decorator to run async commands"""
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# Apply async wrapper to all commands
# Note: Must manually list commands since Click decorators hide the async nature
async_commands = [init, start, stop, status, health, clean, purge, hardstop, down]
for cmd in async_commands:
    cmd.callback = async_command(cmd.callback)