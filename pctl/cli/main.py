#!/usr/bin/env python3
"""
pctl - PAIC Control CLI
Main entry point for the unified testing CLI
"""

import click

from .token import token
from .elk import elk

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
    click.echo("pctl version 0.1.0")

# Add subcommand groups
cli.add_command(token)
cli.add_command(elk)

if __name__ == '__main__':
    cli()