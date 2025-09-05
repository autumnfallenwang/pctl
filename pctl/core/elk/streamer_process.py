#!/usr/bin/env python3
"""
ELK Log Streamer Process - Adapted from original PAIC streamer
Streams Frodo JSON logs to Elasticsearch with pure passthrough
"""

import asyncio
import json
import signal
import sys
import subprocess
import argparse
import os
import atexit
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import httpx
from loguru import logger


class StreamerProcess:
    """
    Log streamer adapted from original PAIC streamer with modern async patterns
    Key features from original:
    - Pure JSON passthrough (no metadata addition)
    - Bulk Elasticsearch indexing with buffer management
    - Background daemon mode with PID files
    - Graceful shutdown handling
    """
    
    def __init__(self, 
                 environment: str,
                 frodo_cmd: List[str],
                 elasticsearch_url: str = "http://localhost:9200",
                 batch_size: int = 50,
                 flush_interval: int = 5,
                 template_name: str = "paic-logs-template",
                 verbose: bool = False):
        
        self.environment = environment
        self.frodo_cmd = frodo_cmd
        self.es_url = elasticsearch_url.rstrip('/')
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.template_name = template_name
        self.verbose = verbose
        
        # Buffer for bulk operations (adapted from original)
        self.buffer: List[Dict[str, Any]] = []
        self.last_flush = datetime.now()
        
        # Process control
        self.running = False
        self.frodo_process: Optional[asyncio.subprocess.Process] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # Index naming pattern from original: paic-logs-{environment}
        self.index_name = f"paic-logs-{environment}"
        
        # Setup logging
        if verbose:
            logger.remove()
            logger.add(sys.stderr, level="DEBUG")
    
    def log_message(self, message: str) -> None:
        """Log message with timestamp (adapted from original)"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        logger.info(log_line)
    
    def setup_signal_handlers(self) -> None:
        """Setup graceful shutdown on SIGINT/SIGTERM (from original)"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals gracefully (from original)"""
        self.log_message(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    async def verify_index_template(self) -> bool:
        """Verify that the required index template exists (from original)"""
        try:
            response = await self.http_client.get(f"{self.es_url}/_index_template/{self.template_name}")
            if response.status_code == 200:
                result = response.json()
                if result.get('index_templates'):
                    self.log_message(f"Using index template: {self.template_name}")
                    return True
                else:
                    self.log_message(f"⚠️  Index template '{self.template_name}' not found - using ES defaults")
                    return False
        except Exception as e:
            self.log_message(f"⚠️  Could not verify index template '{self.template_name}': {e}")
            return False
    
    def parse_log_entry(self, log_line: str) -> Optional[Dict[str, Any]]:
        """Parse and normalize payload - handle both string and object payloads"""
        try:
            # Parse JSON from Frodo CLI output
            doc = json.loads(log_line.strip())
            
            # Normalize payload based on type
            if doc.get("type") == "text/plain" and isinstance(doc.get("payload"), str):
                # Wrap string payload in object with "message" key
                doc["payload"] = {"message": doc["payload"]}
            elif doc.get("type") == "application/json":
                # Already an object, leave as-is
                pass
            
            return doc
        except json.JSONDecodeError:
            # Skip non-JSON lines (like header messages)
            return None
    
    async def bulk_index(self, documents: List[Dict[str, Any]]) -> bool:
        """Send batch of documents to Elasticsearch (adapted from original)"""
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
            response = await self.http_client.post(
                f"{self.es_url}/_bulk",
                content=bulk_data,
                headers={'Content-Type': 'application/x-ndjson'}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errors'):
                    # Log detailed error information 
                    self.log_message(f"Bulk indexing had errors: True")
                    
                    # Show first few error details for debugging
                    error_items = []
                    for item in result.get('items', []):
                        if 'index' in item and 'error' in item['index']:
                            error_detail = item['index']['error']
                            error_items.append(f"Type: {error_detail.get('type', 'unknown')}, Reason: {error_detail.get('reason', 'unknown')}")
                            if len(error_items) >= 3:  # Limit to first 3 errors
                                break
                    
                    if error_items:
                        self.log_message(f"Sample errors: {'; '.join(error_items)}")
                    
                    return False
                else:
                    indexed_count = len([item for item in result['items'] if 'index' in item])
                    self.log_message(f"Successfully indexed {indexed_count} documents")
                    return True
            else:
                self.log_message(f"Failed to bulk index documents: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            self.log_message(f"Failed to bulk index documents: {e}")
            return False
    
    async def flush_buffer(self) -> bool:
        """Flush current buffer to Elasticsearch (from original)"""
        if self.buffer:
            self.log_message(f"Flushing {len(self.buffer)} documents to Elasticsearch...")
            success = await self.bulk_index(self.buffer)
            if success:
                self.buffer.clear()
                self.last_flush = datetime.now()
            return success
        return True
    
    async def start_streaming(self) -> None:
        """Start streaming logs from Frodo CLI (adapted from original)"""
        self.running = True
        self.setup_signal_handlers()
        
        # Initialize HTTP client
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        try:
            # Verify index template exists (from original)
            await self.verify_index_template()
            
            # Start periodic flush task
            flush_task = asyncio.create_task(self._periodic_flush())
            
            # Start Frodo process
            self.log_message(f"Starting Frodo CLI: {' '.join(self.frodo_cmd)}")
            
            self.frodo_process = await asyncio.create_subprocess_exec(
                *self.frodo_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024*1024  # 1MB buffer limit to handle large log lines
            )
            
            self.log_message("Log streaming started. Processing lines...")
            
            # Process log lines in real-time (adapted from original)
            while self.running:
                try:
                    line = await self.frodo_process.stdout.readline()
                    if not line:
                        break
                    
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        doc = self.parse_log_entry(line_str)
                        if doc:  # Only add valid JSON documents
                            self.buffer.append(doc)
                            
                            # Flush buffer if it reaches batch size (from original)
                            if len(self.buffer) >= self.batch_size:
                                await self.flush_buffer()
                                
                except Exception as e:
                    self.log_message(f"Error reading line from Frodo: {e}")
                    # Continue processing - don't let one bad line kill the streamer
                    await asyncio.sleep(1)
                    continue
            
        except Exception as e:
            self.log_message(f"Error during streaming: {e}")
        finally:
            # Cleanup (adapted from original)
            self.running = False
            
            # Cancel flush task gracefully
            flush_task.cancel()
            try:
                await flush_task
            except asyncio.CancelledError:
                pass  # Expected when canceling
            
            # Final flush
            await self.flush_buffer()
            
            if self.frodo_process:
                self.frodo_process.terminate()
                await self.frodo_process.wait()
            
            if self.http_client:
                await self.http_client.aclose()
            
            self.log_message("PAIC Streamer stopped.")
    
    async def _periodic_flush(self) -> None:
        """Periodic buffer flush (adapted from original timer logic)"""
        while self.running:
            await asyncio.sleep(self.flush_interval)
            
            if self.buffer and (datetime.now() - self.last_flush).total_seconds() >= self.flush_interval:
                await self.flush_buffer()


async def main():
    """CLI entry point for streamer process"""
    parser = argparse.ArgumentParser(description='ELK Log Streamer Process')
    parser.add_argument('--environment', required=True, help='Environment name')
    parser.add_argument('--elasticsearch-url', default='http://localhost:9200', help='Elasticsearch URL')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for bulk indexing')
    parser.add_argument('--flush-interval', type=int, default=5, help='Buffer flush interval in seconds')
    parser.add_argument('--template-name', default='paic-logs-template', help='Index template name')
    parser.add_argument('--log-file', help='Log file path for background mode')
    parser.add_argument('--pid-file', help='PID file path for background mode')
    parser.add_argument('--frodo-cmd', required=True, help='Frodo command to execute (space-separated)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Handle background mode setup (adapted from original)
    if args.pid_file and args.log_file:
        # Write PID file
        with open(args.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        
        # Setup cleanup on exit
        def cleanup_pid_file():
            try:
                if os.path.exists(args.pid_file):
                    os.remove(args.pid_file)
            except:
                pass
        atexit.register(cleanup_pid_file)
        
        # Redirect stdout/stderr to log file if provided
        if args.log_file:
            log_file = open(args.log_file, 'a')
            os.dup2(log_file.fileno(), sys.stdout.fileno())
            os.dup2(log_file.fileno(), sys.stderr.fileno())
    
    # Parse frodo command
    frodo_cmd = args.frodo_cmd.split()
    
    # Create and start streamer
    streamer = StreamerProcess(
        environment=args.environment,
        frodo_cmd=frodo_cmd,
        elasticsearch_url=args.elasticsearch_url,
        batch_size=args.batch_size,
        flush_interval=args.flush_interval,
        template_name=args.template_name,
        verbose=args.verbose
    )
    
    try:
        await streamer.start_streaming()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())