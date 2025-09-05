#!/usr/bin/env python3
"""
StreamerRegistry - JSON-based process tracking for ELK streamers
Replaces PID file management with centralized JSON registry
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import tempfile

from loguru import logger


@dataclass
class StreamerEntry:
    """Single streamer process entry in registry"""
    environment: str
    pid: Optional[int]  # None when stopped
    status: str  # "running" | "stopped"
    start_time: str  # ISO format
    stop_time: Optional[str]  # ISO format, None when running
    components: List[str]
    log_level: int
    log_file: str
    frodo_cmd: List[str]
    elasticsearch_url: str
    batch_size: int
    flush_interval: int
    
    @classmethod
    def from_dict(cls, data: dict) -> "StreamerEntry":
        """Create entry from dictionary"""
        return cls(**data)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class StreamerRegistry:
    """
    Centralized JSON-based registry for ELK streamer processes
    Replaces scattered PID files with single registry file
    """
    
    def __init__(self, registry_dir: Optional[Path] = None, logs_dir: Optional[Path] = None):
        """
        Initialize registry with configurable paths
        
        Args:
            registry_dir: Directory for registry file (default: ~/.local/share/pctl/)
            logs_dir: Directory for log files (default: ~/.local/share/pctl/logs/)
        """
        # Default paths follow XDG Base Directory spec
        self.registry_dir = registry_dir or (Path.home() / ".local" / "share" / "pctl")
        self.logs_dir = logs_dir or (self.registry_dir / "logs")
        
        # Ensure directories exist
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.registry_file = self.registry_dir / "streamers.json"
        
        # Initialize empty registry if doesn't exist
        if not self.registry_file.exists():
            self._write_registry({})
    
    def _read_registry(self) -> Dict[str, dict]:
        """Safely read registry file"""
        try:
            if not self.registry_file.exists():
                return {}
            
            content = self.registry_file.read_text(encoding='utf-8')
            return json.loads(content) if content.strip() else {}
            
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read streamer registry: {e}")
            return {}
    
    def _write_registry(self, data: Dict[str, dict], retries: int = 3) -> None:
        """Safely write registry file with atomic operation"""
        for attempt in range(retries):
            try:
                # Write to temporary file first (atomic operation)
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    dir=self.registry_dir,
                    delete=False,
                    suffix='.tmp',
                    encoding='utf-8'
                ) as temp_file:
                    json.dump(data, temp_file, indent=2, ensure_ascii=False)
                    temp_file.flush()
                    
                    # Atomic rename (on most filesystems)
                    Path(temp_file.name).rename(self.registry_file)
                    return
                    
            except OSError as e:
                if attempt == retries - 1:
                    logger.error(f"Failed to write streamer registry after {retries} attempts: {e}")
                    raise
                else:
                    logger.debug(f"Registry write attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(0.1)  # Brief delay before retry
    
    def register_streamer(self,
                         environment: str,
                         pid: int,
                         components: List[str],
                         log_level: int,
                         frodo_cmd: List[str],
                         elasticsearch_url: str,
                         batch_size: int,
                         flush_interval: int) -> str:
        """
        Register a new streamer process
        
        Returns:
            Log file path for the streamer
        """
        # Generate log file path
        log_file = self.logs_dir / f"pctl_streamer_{environment}.log"
        
        # Create registry entry
        entry = StreamerEntry(
            environment=environment,
            pid=pid,
            status="running",
            start_time=datetime.now(timezone.utc).isoformat(),
            stop_time=None,
            components=components,
            log_level=log_level,
            log_file=str(log_file),
            frodo_cmd=frodo_cmd,
            elasticsearch_url=elasticsearch_url,
            batch_size=batch_size,
            flush_interval=flush_interval
        )
        
        # Update registry
        data = self._read_registry()
        data[environment] = entry.to_dict()
        self._write_registry(data)
        
        logger.debug(f"Registered streamer for {environment} (PID {pid})")
        return str(log_file)
    
    def get_streamer(self, environment: str) -> Optional[StreamerEntry]:
        """Get streamer entry for environment"""
        data = self._read_registry()
        entry_dict = data.get(environment)
        
        if entry_dict:
            try:
                return StreamerEntry.from_dict(entry_dict)
            except (TypeError, ValueError) as e:
                logger.warning(f"Invalid registry entry for {environment}: {e}")
                # Clean up invalid entry
                self.unregister_streamer(environment)
        
        return None
    
    def list_streamers(self) -> List[StreamerEntry]:
        """List all registered streamers"""
        data = self._read_registry()
        entries = []
        
        for env, entry_dict in data.items():
            try:
                entries.append(StreamerEntry.from_dict(entry_dict))
            except (TypeError, ValueError) as e:
                logger.warning(f"Invalid registry entry for {env}: {e}")
                # Note: Don't clean up here to avoid modifying during iteration
        
        return entries
    
    def stop_streamer(self, environment: str) -> bool:
        """
        Mark streamer as stopped (keep entry in registry)
        
        Returns:
            True if entry existed and was updated, False otherwise
        """
        data = self._read_registry()
        
        if environment in data:
            data[environment]["status"] = "stopped"
            data[environment]["stop_time"] = datetime.now(timezone.utc).isoformat()
            data[environment]["pid"] = None
            self._write_registry(data)
            logger.debug(f"Marked streamer as stopped for {environment}")
            return True
        
        return False
    
    def unregister_streamer(self, environment: str) -> bool:
        """
        Completely remove streamer from registry (for purge/down)
        
        Returns:
            True if entry existed and was removed, False otherwise
        """
        data = self._read_registry()
        
        if environment in data:
            del data[environment]
            self._write_registry(data)
            logger.debug(f"Unregistered streamer for {environment}")
            return True
        
        return False
    
    def cleanup_dead_processes(self) -> int:
        """
        Mark running processes as stopped if they no longer exist
        
        Returns:
            Number of entries cleaned up
        """
        data = self._read_registry()
        cleaned_count = 0
        
        for env, entry_dict in data.items():
            try:
                # Only check processes marked as running
                if entry_dict.get('status') == 'running':
                    pid = entry_dict.get('pid')
                    if pid:
                        try:
                            os.kill(pid, 0)  # Raises OSError if process doesn't exist
                        except OSError:
                            # Process doesn't exist, mark as stopped
                            entry_dict['status'] = 'stopped'
                            entry_dict['stop_time'] = datetime.now(timezone.utc).isoformat()
                            entry_dict['pid'] = None
                            cleaned_count += 1
                            logger.debug(f"Marked dead process as stopped for {env}")
                        
            except Exception as e:
                logger.debug(f"Error checking process {entry_dict.get('pid', 'unknown')} for {env}: {e}")
                # Mark as stopped on any error
                entry_dict['status'] = 'stopped'
                entry_dict['stop_time'] = datetime.now(timezone.utc).isoformat()
                entry_dict['pid'] = None
                cleaned_count += 1
        
        if cleaned_count > 0:
            self._write_registry(data)
            logger.info(f"Marked {cleaned_count} dead processes as stopped")
        
        return cleaned_count
    
    def get_log_file_path(self, environment: str) -> Path:
        """Get log file path for environment (whether registered or not)"""
        return self.logs_dir / f"pctl_streamer_{environment}.log"
    
    def clear_all_streamers(self) -> int:
        """
        Remove all streamers from registry (for down command)
        
        Returns:
            Number of entries removed
        """
        data = self._read_registry()
        count = len(data)
        
        if count > 0:
            self._write_registry({})
            logger.info(f"Cleared {count} streamers from registry")
        
        return count
    
    def get_registry_info(self) -> dict:
        """Get registry metadata for debugging"""
        return {
            "registry_file": str(self.registry_file),
            "logs_directory": str(self.logs_dir),
            "total_entries": len(self._read_registry()),
            "registry_exists": self.registry_file.exists(),
            "logs_dir_exists": self.logs_dir.exists()
        }