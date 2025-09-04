"""
Pydantic models for ELK status and configuration
"""

from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class HealthStatus(str, Enum):
    """ELK infrastructure health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    UNHEALTHY = "unhealthy"
    NOT_FOUND = "not_found"
    STOPPED = "stopped"


class ELKHealth(BaseModel):
    """ELK infrastructure health information"""
    containers_exist: bool = Field(..., description="Docker containers found")
    containers_running: bool = Field(..., description="Docker containers are running")
    elasticsearch_healthy: bool = Field(..., description="Elasticsearch responding and healthy")
    kibana_available: bool = Field(..., description="Kibana API responding")
    overall_status: HealthStatus = Field(..., description="Overall infrastructure status")
    elasticsearch_version: Optional[str] = Field(default=None, description="ES version if available")
    platform_name: str = Field(..., description="Detected platform")


class StreamerStatus(BaseModel):
    """Individual environment streamer status"""
    environment: str = Field(..., description="Environment name")
    process_running: bool = Field(..., description="Streamer process is running")
    pid: Optional[int] = Field(default=None, description="Process ID if running")
    log_file_path: Optional[str] = Field(default=None, description="Path to log file")
    log_file_size: Optional[str] = Field(default=None, description="Log file size")
    last_activity: Optional[datetime] = Field(default=None, description="Last log entry time")
    index_doc_count: Optional[int] = Field(default=None, description="Document count in ES indices")
    index_size: Optional[str] = Field(default=None, description="Storage used by indices")


class ProcessInfo(BaseModel):
    """Background process information"""
    pid: int = Field(..., description="Process ID")
    log_file: str = Field(..., description="Log file path")
    pid_file: str = Field(..., description="PID file path")
    environment: str = Field(..., description="Environment name")


class ELKConfig(BaseModel):
    """ELK configuration parameters"""
    log_level: int = Field(default=2, ge=1, le=4, description="Frodo log level (1-4)")
    component: str = Field(default="idm-core", description="Log component(s)")
    batch_size: int = Field(default=50, description="Elasticsearch bulk batch size")
    flush_interval: int = Field(default=5, description="Buffer flush interval in seconds")
    elasticsearch_url: str = Field(default="http://localhost:9200", description="ES URL")
    template_name: str = Field(default="paic-logs-template", description="ES template name")
    verbose: bool = Field(default=False, description="Enable verbose logging")


class CommandResult(BaseModel):
    """Result of subprocess command execution"""
    stdout: str = Field(..., description="Standard output")
    stderr: str = Field(..., description="Standard error") 
    returncode: int = Field(..., description="Exit code")
    success: bool = Field(..., description="Command succeeded")
    
    @classmethod
    def from_process(cls, stdout: bytes, stderr: bytes, returncode: int) -> 'CommandResult':
        """Create from subprocess result"""
        return cls(
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace'), 
            returncode=returncode,
            success=returncode == 0
        )