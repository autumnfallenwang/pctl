#!/usr/bin/env python3
"""
pctl - PAIC Control CLI
Main entry point for the unified testing CLI
"""

import click
from rich.console import Console

from .token import token

console = Console()

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
    console.print("pctl version 0.1.0")

# Add subcommand groups
cli.add_command(token)

if __name__ == '__main__':
    cli()