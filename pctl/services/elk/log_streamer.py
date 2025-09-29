#!/usr/bin/env python3
"""
ELK Log Streamer Service - Modernized to use PAICLogService instead of Frodo subprocess
Moved from core/elk to services/elk (proper Service Layer location)
Streams PAIC logs to Elasticsearch with pure JSON passthrough
"""

import asyncio
import json
import signal
import sys
import argparse
import os
import atexit
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
from ...core.http_client import HTTPClient

from ..conn.log_service import PAICLogService


class LogStreamer:
    """
    Log streamer service - Business Logic for streaming logs to Elasticsearch
    Service Layer: Can access PAICLogService and coordinate workflows
    """

    def __init__(self,
                 profile_name: str,
                 source: str,
                 level: int,
                 elasticsearch_url: str = "http://localhost:9200",
                 batch_size: int = 50,
                 flush_interval: int = 5,
                 template_name: str = "paic-logs-template",
                 verbose: bool = False):

        self.profile_name = profile_name
        self.source = source
        self.level = level
        self.es_url = elasticsearch_url.rstrip('/')
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.template_name = template_name
        self.verbose = verbose

        # Use PAICLogService instead of Frodo subprocess
        self.log_service = PAICLogService()

        # Buffer for bulk operations (same as original)
        self.buffer: List[Dict[str, Any]] = []

        # Runtime state
        self.running = False
        self.http_client: Optional[HTTPClient] = None

        # Dynamic index name based on profile
        self.index_name = f"paic-logs-{self.profile_name}-{datetime.now().strftime('%Y.%m')}"

    def log_message(self, message: str, level: str = "INFO") -> None:
        """Log message (same interface as original)"""
        timestamp = datetime.now().isoformat()
        formatted_msg = f"[{timestamp}] {level}: {message}"

        if self.verbose:
            print(formatted_msg, flush=True)

        # Also log to loguru
        if level == "ERROR":
            logger.error(message)
        elif level == "DEBUG":
            logger.debug(message)
        else:
            logger.info(message)

    def setup_signal_handlers(self) -> None:
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            self.log_message(f"Received signal {signum}, shutting down gracefully...")
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def parse_log_entry(self, log_json: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON log entry from PAICLogService
        Same interface as original but input is already JSON from PAICLogService
        """
        try:
            # PAICLogService already gives us JSON strings
            doc = json.loads(log_json.strip())

            # Normalize payload based on type (same logic as original)
            if doc.get("type") == "text/plain" and isinstance(doc.get("payload"), str):
                # Wrap string payload in object with "message" key
                doc["payload"] = {"message": doc["payload"]}
            elif doc.get("type") == "application/json":
                # Already an object, leave as-is
                pass

            return doc
        except json.JSONDecodeError:
            # Skip invalid JSON (though PAICLogService should always give valid JSON)
            return None

    async def bulk_index(self, documents: List[Dict[str, Any]]) -> bool:
        """Send batch of documents to Elasticsearch (same as original)"""
        if not documents:
            return True

        # Create bulk request body (same pattern as original)
        bulk_body = []
        for doc in documents:
            # Index action
            bulk_body.append(json.dumps({
                "index": {"_index": self.index_name}
            }))
            # Document (pure JSON passthrough)
            bulk_body.append(json.dumps(doc))

        bulk_data = '\n'.join(bulk_body) + '\n'

        try:
            response = await self.http_client.post_response(
                f"{self.es_url}/_bulk",
                content=bulk_data,
                headers={'Content-Type': 'application/x-ndjson'}
            )

            if response.is_success():
                result = response.json()
                if result.get('errors'):
                    # Log detailed error information
                    self.log_message(f"Bulk indexing had errors: True")

                    # Show first few error details for debugging
                    error_items = []
                    for item in result.get('items', []):
                        if 'index' in item and 'error' in item['index']:
                            error_items.append(item['index']['error'])
                            if len(error_items) >= 3:  # Limit to first 3 errors
                                break

                    if error_items:
                        self.log_message(f"First few errors: {error_items}")

                    return False
                else:
                    # Success
                    self.log_message(f"Indexed {len(documents)} documents to {self.index_name}", "DEBUG")
                    return True
            else:
                self.log_message(f"Bulk index failed with status {response.status_code}: {response.text}")
                return False

        except Exception as e:
            self.log_message(f"Error during bulk indexing: {e}", "ERROR")
            return False

    async def flush_buffer(self) -> None:
        """Flush current buffer to Elasticsearch (same as original)"""
        if self.buffer:
            success = await self.bulk_index(self.buffer)
            if success:
                self.log_message(f"Flushed {len(self.buffer)} documents", "DEBUG")
            else:
                self.log_message(f"Failed to flush {len(self.buffer)} documents", "ERROR")

            # Clear buffer regardless of success (prevent infinite retries)
            self.buffer.clear()

    async def _periodic_flush(self) -> None:
        """Periodic buffer flush task (same as original)"""
        while self.running:
            await asyncio.sleep(self.flush_interval)
            if self.buffer:
                await self.flush_buffer()

    async def verify_index_template(self) -> None:
        """Verify Elasticsearch index template exists (same as original)"""
        try:
            response = await self.http_client.get_response(f"{self.es_url}/_index_template/{self.template_name}")

            if response.status_code == 404:
                self.log_message(f"Index template '{self.template_name}' not found - continuing without template", "DEBUG")
            elif response.is_success():
                self.log_message(f"Index template '{self.template_name}' verified", "DEBUG")
            else:
                self.log_message(f"Unexpected response checking template: {response.status_code}")

        except Exception as e:
            self.log_message(f"Error verifying index template: {e}", "DEBUG")
            # Continue anyway - template is optional

    async def start_streaming(self) -> None:
        """Start streaming logs from PAICLogService (modernized from Frodo subprocess)"""
        self.running = True
        self.setup_signal_handlers()

        # Initialize HTTP client
        self.http_client = HTTPClient(timeout=30)

        try:
            # Verify index template exists (from original)
            await self.verify_index_template()

            # Start periodic flush task
            flush_task = asyncio.create_task(self._periodic_flush())

            # Start PAIC log streaming (replaces Frodo subprocess)
            self.log_message(f"Starting PAIC log streaming: profile={self.profile_name}, source={self.source}, level={self.level}")

            # Stream logs from PAICLogService (replaces Frodo subprocess reading)
            async for log_json in self.log_service.stream_logs(
                profile_name=self.profile_name,
                source=self.source,
                level=self.level,
                use_default_noise_filter=True
            ):
                if not self.running:
                    break

                try:
                    # Parse log entry (PAICLogService gives us JSON strings)
                    doc = self.parse_log_entry(log_json)
                    if doc:  # Only add valid JSON documents
                        self.buffer.append(doc)

                        # Flush buffer if it reaches batch size (from original)
                        if len(self.buffer) >= self.batch_size:
                            await self.flush_buffer()

                except Exception as e:
                    self.log_message(f"Error processing log entry: {e}")
                    # Continue processing - don't let one bad entry kill the streamer
                    continue

            self.log_message("PAIC log stream ended")

        except Exception as e:
            self.log_message(f"Error during streaming: {e}")
        finally:
            # Cleanup (same as original)
            self.running = False

            # Cancel flush task gracefully
            flush_task.cancel()
            try:
                await flush_task
            except asyncio.CancelledError:
                pass

            # Final buffer flush
            if self.buffer:
                self.log_message("Performing final buffer flush...")
                await self.flush_buffer()

            # HTTP client cleanup (HTTPClient doesn't need explicit close)

            self.log_message("Log streaming stopped")


async def main():
    """Main entry point for streamer process (compatible with original args)"""
    parser = argparse.ArgumentParser(description="PAIC Log Streamer (modernized)")

    # Updated arguments for PAICLogService
    parser.add_argument("--profile-name", required=True, help="Connection profile name")
    parser.add_argument("--source", required=True, help="Log source to stream")
    parser.add_argument("--level", type=int, default=2, help="Log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL)")
    parser.add_argument("--elasticsearch-url", default="http://localhost:9200", help="Elasticsearch URL")
    parser.add_argument("--batch-size", type=int, default=50, help="Bulk indexing batch size")
    parser.add_argument("--flush-interval", type=int, default=5, help="Buffer flush interval (seconds)")
    parser.add_argument("--template-name", default="paic-logs-template", help="Elasticsearch template name")
    parser.add_argument("--log-file", help="Log file path (for compatibility)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    # Legacy arguments for backward compatibility (ignored)
    parser.add_argument("--environment", help="Environment name (legacy, ignored)")
    parser.add_argument("--frodo-cmd", help="Frodo command (legacy, ignored)")

    args = parser.parse_args()

    # Configure logging output to file if specified
    if args.log_file:
        logger.add(args.log_file, rotation="10 MB", retention="7 days")

    # Create and start streamer
    streamer = LogStreamer(
        profile_name=args.profile_name,
        source=args.source,
        level=args.level,
        elasticsearch_url=args.elasticsearch_url,
        batch_size=args.batch_size,
        flush_interval=args.flush_interval,
        template_name=args.template_name,
        verbose=args.verbose
    )

    try:
        await streamer.start_streaming()
    except KeyboardInterrupt:
        logger.info("Streamer interrupted by user")
    except Exception as e:
        logger.error(f"Streamer crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())