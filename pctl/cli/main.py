#!/usr/bin/env python3
"""
pctl - PAIC Control CLI
Main entry point for the unified testing CLI
"""

import click

from .token import token
from .journey import journey
from .elk import elk
from .conn import conn
from ..core.version import get_version

@click.group()
@click.option('--config', type=click.Path(exists=True), help='Config file path')
@click.pass_context
def cli(ctx, config):
    """PAIC Control - Unified testing CLI for token, journey, and ELK management"""
    ctx.ensure_object(dict)
    ctx.obj['config'] = config

@cli.command()
def version():
    """Show version information"""
    version_str = get_version()
    click.echo(f"pctl version {version_str}")

# Add subcommand groups
cli.add_command(token)
cli.add_command(journey)
cli.add_command(elk)
cli.add_command(conn)

if __name__ == '__main__':
    cli()