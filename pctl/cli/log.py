"""
Log CLI Commands - Historical log analysis
"""

import asyncio
import json
from typing import Optional
from datetime import datetime, timedelta, timezone

import click

from ..services.conn.log_service import PAICLogService
from ..core.exceptions import ServiceError
from ..core.logger import setup_logger


@click.group()
def log():
    """📜 Historical log analysis"""
    pass


@log.command()
@click.argument("conn_name")
@click.option("-c", "--component", default="idm-config",
              help="Log source/component [default: idm-config]")
@click.option("--from", "from_ts",
              help="Start time (YYYY-MM-DD or ISO-8601, ignored if --days given)")
@click.option("--to", "to_ts",
              help="End time (YYYY-MM-DD or ISO-8601, ignored if --days given)")
@click.option("--days", type=int, default=1,
              help="Search last N days (from N days ago to now, ignores --from/--to) [default: 1]")
@click.option("-q", "--query",
              help="PAIC query filter expression")
@click.option("--txid",
              help="Transaction ID filter")
@click.option("-l", "--log-level", type=click.IntRange(1, 4), default=2,
              help="Log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL) [default: 2]")
@click.option("--no-default-noise-filter", is_flag=True,
              help="Disable default noise filtering")
@click.option("--page-size", type=click.IntRange(1, 1000), default=1000,
              help="Logs per page (1-1000) [default: 1000]")
@click.option("--max-pages", type=int, default=100,
              help="Max pages per window [default: 100]")
@click.option("--max-retries", type=int, default=4,
              help="Max retry attempts on 429 [default: 4]")
@click.option("-f", "--format", "output_format",
              type=click.Choice(["jsonl", "json"], case_sensitive=False),
              default="jsonl",
              help="Output format [default: jsonl]")
@click.option("-o", "--output",
              type=click.Path(),
              help="Save to file (default: stdout/console)")
@click.option("-v", "--verbose", is_flag=True,
              help="Enable verbose logging")
async def search(
    conn_name: str,
    component: str,
    from_ts: Optional[str],
    to_ts: Optional[str],
    days: Optional[int],
    query: Optional[str],
    txid: Optional[str],
    log_level: int,
    no_default_noise_filter: bool,
    page_size: int,
    max_pages: int,
    max_retries: int,
    output_format: str,
    output: Optional[str],
    verbose: bool
):
    """Search historical logs from PAIC

    Examples:

      # Last 24h from idm-config (all defaults)
      pctl log search myenv

      # Last 7 days with filter
      pctl log search myenv -c idm-config --days 7 -q '/payload/objectId co "endpoint/"'

      # Specific date range
      pctl log search myenv -c am-access --from 2025-10-01 --to 2025-10-06

      # Save to file
      pctl log search myenv -c idm-config --days 7 -o logs.jsonl

      # Beautiful JSON for human reading
      pctl log search myenv -c idm-config --format json -o report.json
    """

    # Setup logging
    log_level_str = "DEBUG" if verbose else "INFO"
    setup_logger(log_level_str)

    try:
        # Parse time parameters
        start_ts, end_ts = _parse_time_parameters(from_ts, to_ts, days)

        if verbose:
            click.echo(f"Searching logs from connection: {conn_name}")
            click.echo(f"Component: {component}")
            if start_ts:
                click.echo(f"Start: {start_ts}")
            if end_ts:
                click.echo(f"End: {end_ts}")
            if query:
                click.echo(f"Query filter: {query}")
            click.echo()

        # Create service and fetch logs
        service = PAICLogService()

        result = await service.fetch_historical_logs(
            profile_name=conn_name,
            source=component,
            start_ts=start_ts,
            end_ts=end_ts,
            query_filter=query,
            transaction_id=txid,
            level=log_level,
            use_default_noise_filter=not no_default_noise_filter,
            page_size=page_size,
            max_pages_per_window=max_pages,
            max_retries=max_retries
        )

        if not result["success"]:
            click.echo(f"❌ Failed to fetch logs: {result.get('error', 'Unknown error')}", err=True)
            raise click.Abort()

        # Display summary if verbose
        if verbose:
            click.echo(f"✅ Fetched {result['total_logs']} logs")
            click.echo(f"   Pages: {result['total_pages']}")
            click.echo(f"   Windows: {result['total_windows']}")
            click.echo(f"   Time range: {result['time_range']['valid_days']:.1f} days")
            if result['time_range']['skipped_days'] > 0:
                click.echo(f"   ⚠️  Skipped {result['time_range']['skipped_days']:.1f} days (beyond retention)")
            click.echo()

        # Format and output
        output_content = _format_output(result, output_format)

        if output:
            # Write to file
            with open(output, 'w') as f:
                f.write(output_content)
            click.echo(f"✅ Saved {result['total_logs']} logs to {output}")
        else:
            # Write to stdout
            click.echo(output_content)

    except ServiceError as e:
        click.echo(f"❌ Service error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        raise click.Abort()


def _parse_time_parameters(
    from_ts: Optional[str],
    to_ts: Optional[str],
    days: Optional[int]
) -> tuple[Optional[str], Optional[str]]:
    """Parse time parameters and return start_ts, end_ts"""

    if days:
        # --days takes precedence, ignore --from/--to
        now = datetime.now(timezone.utc)
        end_time = now
        start_time = now - timedelta(days=days)

        return (
            start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )

    # Parse --from and --to if provided
    start_ts_parsed = _parse_timestamp(from_ts) if from_ts else None
    end_ts_parsed = _parse_timestamp(to_ts) if to_ts else None

    return start_ts_parsed, end_ts_parsed


def _parse_timestamp(date_str: str) -> str:
    """Parse user input to ISO-8601 timestamp

    Supports:
    - Simple date: 2025-10-01 → 2025-10-01T00:00:00.000Z
    - ISO-8601: 2025-10-01T12:30:00.000Z → use as-is
    - ISO-8601 without Z: 2025-10-01T12:30:00 → add .000Z
    """
    if not date_str:
        return None

    # Already has 'T' - ISO-8601 format
    if 'T' in date_str:
        # Ensure it ends with Z (UTC)
        if not date_str.endswith('Z'):
            # Check if has milliseconds
            if '.' not in date_str.split('T')[1]:
                return f"{date_str}.000Z"
            else:
                return f"{date_str}Z"
        return date_str
    else:
        # Simple date format YYYY-MM-DD → start of day UTC
        return f"{date_str}T00:00:00.000Z"


def _format_output(result: dict, output_format: str) -> str:
    """Format result based on output format choice"""

    if output_format == "jsonl":
        # JSON Lines - one log per line (no metadata)
        lines = []
        for log in result["logs"]:
            lines.append(json.dumps(log, separators=(',', ':')))
        return '\n'.join(lines)

    elif output_format == "json":
        # Beautiful JSON with metadata
        return json.dumps(result, indent=2, ensure_ascii=False)

    else:
        raise ValueError(f"Unknown output format: {output_format}")


# Async command wrapper
def async_command(f):
    """Decorator to run async commands"""
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# Apply async wrapper to commands
search.callback = async_command(search.callback)
