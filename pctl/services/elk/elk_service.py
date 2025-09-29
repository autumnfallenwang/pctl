"""
ELK Service - Internal API for ELK stack management
"""

import asyncio
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

from ...core.elk.elk_models import ELKHealth, StreamerStatus, ProcessInfo, ELKConfig, HealthStatus
from ...core.elk.platform import PlatformDetector
from .streamer_manager import StreamerManager
from ...core.http_client import HTTPClient
from ...core.exceptions import ELKError, ServiceError
from ...core.config import ConfigLoader
from ...core.subprocess_runner import SubprocessRunner
from ..conn.conn_service import ConnectionService
from ..conn.log_service import PAICLogService


class ELKService:
    """Service for ELK stack management with internal APIs"""
    
    def __init__(self, config_dir: Optional[str] = None, require_config: bool = True):
        self.logger = logger
        self.platform_detector = PlatformDetector()
        self.config_loader = ConfigLoader()
        self.streamer_manager = StreamerManager()
        self.http_client = HTTPClient()
        self.subprocess_runner = SubprocessRunner()
        # Service-to-service communication (following domain boundaries)
        self.connection_service = ConnectionService()
        self.log_service = PAICLogService()
        
        # Smart config path resolution for deployment
        if require_config:
            self.base_config_path = self._resolve_config_path(config_dir)
        else:
            # For commands that don't need config, use simple defaults
            self.base_config_path = None
    
    def _resolve_config_path(self, config_dir: Optional[str] = None) -> Path:
        """Resolve config path with deployment-friendly logic"""
        
        if config_dir:
            # User-provided config directory
            config_path = Path(config_dir) / "elk"
            if config_path.exists():
                self.logger.debug(f"Using user-specified config directory: {config_path}")
                return config_path
            else:
                raise FileNotFoundError(f"Config directory not found: {config_path}")
        
        # Try deployment-friendly paths in order of preference
        deployment_paths = [
            # 1. Next to pctl binary (deployment scenario)
            Path.cwd() / "configs" / "elk",
            
            # 2. Relative to package location
            Path(__file__).parent.parent.parent / "configs" / "elk" if hasattr(Path(__file__), 'parent') else None,
            
            # 3. System config location
            Path("/etc/pctl/configs/elk"),
            Path.home() / ".pctl" / "configs" / "elk",
        ]
        
        for path in deployment_paths:
            if path and path.exists():
                self.logger.debug(f"Found config directory: {path}")
                return path
        
        # If no config found, create default structure next to binary
        default_path = Path.cwd() / "configs" / "elk"
        self.logger.warning(f"⚠️  No config directory found, expecting: {default_path}")
        self.logger.warning("   💡 Solutions:")
        self.logger.warning("      1. Deploy configs/ folder next to pctl binary")
        self.logger.warning("      2. Use --config-dir option: pctl elk --config-dir /path/to/configs init")
        return default_path
    
    # INTERNAL APIs (for cross-command use)
    
    async def check_health(self) -> ELKHealth:
        """Internal API: Check ELK infrastructure health"""
        
        platform_config = self.platform_detector.detect_platform()
        
        # Check if containers exist
        containers_exist = await self._check_containers_exist()
        containers_running = False
        elasticsearch_healthy = False
        kibana_available = False
        elasticsearch_version = None
        
        if containers_exist:
            # Check if containers are running
            containers_running = await self._check_containers_running()
            
            if containers_running:
                # Check service health
                elasticsearch_healthy, elasticsearch_version = await self._check_elasticsearch_health()
                kibana_available = await self._check_kibana_health()
        
        # Determine overall status
        if not containers_exist:
            overall_status = HealthStatus.NOT_FOUND
        elif not containers_running:
            overall_status = HealthStatus.STOPPED
        elif elasticsearch_healthy and kibana_available:
            overall_status = HealthStatus.HEALTHY
        elif elasticsearch_healthy or kibana_available:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.UNHEALTHY
        
        return ELKHealth(
            containers_exist=containers_exist,
            containers_running=containers_running,
            elasticsearch_healthy=elasticsearch_healthy,
            kibana_available=kibana_available,
            overall_status=overall_status,
            elasticsearch_version=elasticsearch_version,
            platform_name=platform_config.name
        )
    
    async def get_status(self, name: str) -> StreamerStatus:
        """Internal API: Get single streamer status by name"""
        
        # Get entry from registry
        entry = self.streamer_manager.get_streamer(name)
        
        # Check if process is running
        process_running = False
        pid = None
        
        if entry:
            if entry.status == "running" and entry.pid:
                pid = entry.pid
                try:
                    # Check if process actually exists
                    import os
                    os.kill(pid, 0)  # Raises OSError if process doesn't exist
                    process_running = True
                    
                except OSError:
                    # Process not running, mark as stopped in registry
                    process_running = False
                    self.streamer_manager.stop_streamer(name)
                    pid = None
            elif entry.status == "stopped":
                process_running = False
                pid = None
        
        # Get log file info
        log_file = self._get_log_file_path(name)
        log_file_size = None
        last_activity = None
        
        if entry:
            # Use registry entry for log file path
            log_file = Path(entry.log_file)
        
        if log_file.exists():
            stat = log_file.stat()
            log_file_size = f"{stat.st_size / 1024:.1f}KB"
            last_activity = stat.st_mtime
        
        # Get Elasticsearch stats (if ELK is healthy)
        index_doc_count = None
        index_size = None
        
        try:
            health = await self.check_health()
            if health.elasticsearch_healthy:
                # Get index stats using connection profile from entry
                if entry:
                    index_doc_count, index_size = await self._get_index_stats(entry.connection_profile)
                else:
                    index_doc_count, index_size = None, None
        except Exception as e:
            self.logger.debug(f"Could not get ES stats for {environment}: {e}")
        
        # Calculate timing information
        start_time_formatted = None
        runtime_or_stopped = None
        components = []
        log_level = None
        
        if entry:
            components = entry.components
            log_level = entry.log_level
            
            # Format start time to local timezone
            from datetime import datetime, timezone
            try:
                start_dt = datetime.fromisoformat(entry.start_time.replace('Z', '+00:00'))
                start_local = start_dt.astimezone()
                start_time_formatted = start_local.strftime("%m/%d %H:%M:%S")
                
                # Calculate runtime or format stop time
                if entry.status == "running" and process_running:
                    runtime = datetime.now(timezone.utc) - start_dt
                    hours, remainder = divmod(int(runtime.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    runtime_or_stopped = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
                elif entry.status == "stopped" and entry.stop_time:
                    stop_dt = datetime.fromisoformat(entry.stop_time.replace('Z', '+00:00'))
                    stop_local = stop_dt.astimezone()
                    runtime_or_stopped = stop_local.strftime("%m/%d %H:%M:%S")
                else:
                    runtime_or_stopped = "Unknown"
            except Exception as e:
                self.logger.debug(f"Error formatting time for {environment}: {e}")
                start_time_formatted = "Unknown"
                runtime_or_stopped = "Unknown"

        return StreamerStatus(
            environment=name,  # Use name as the identifier for display
            connection_profile=entry.connection_profile if entry else "unknown",
            process_running=process_running,
            pid=pid,
            components=components,
            log_level=log_level,
            start_time=start_time_formatted,
            runtime_or_stopped=runtime_or_stopped,
            log_file_path=str(log_file) if entry and log_file.exists() else None,
            log_file_size=log_file_size,
            last_activity=last_activity,
            index_doc_count=index_doc_count,
            index_size=index_size
        )
    
    async def get_all_statuses(self) -> List[StreamerStatus]:
        """Internal API: Get all environment statuses (JSON registry only)"""
        
        # Clean up dead processes first
        self.streamer_manager.cleanup_dead_processes()

        # Get all registered streamers (single source of truth)
        entries = self.streamer_manager.list_streamers()
        
        # Get status for each registered streamer
        statuses = []
        for entry in entries:
            try:
                status = await self.get_status(entry.name)
                statuses.append(status)
            except Exception as e:
                self.logger.error(f"Failed to get status for '{entry.name}': {e}")
        
        return statuses
    
    # PUBLIC APIs (called by CLI)
    
    async def init_stack(self) -> None:
        """Initialize ELK stack (containers + templates + policies)"""
        
        # Check dependencies
        missing_deps = self.platform_detector.check_dependencies()
        if missing_deps:
            raise ELKError(f"Missing dependencies: {', '.join(missing_deps)}")
        
        # Get platform-specific config files
        try:
            docker_compose_path, elk_config_path = self.platform_detector.get_config_files(self.base_config_path)
        except FileNotFoundError as e:
            raise ELKError(str(e))
        
        platform_config = self.platform_detector.detect_platform()
        self.logger.info(f"🖥️  Platform detected: {platform_config.name}")
        self.logger.info(f"🐳 Using Docker Compose: {docker_compose_path.name}")
        self.logger.info(f"⚙️  Using ELK Config: {elk_config_path.name}")
        
        # Check if already running and healthy
        health = await self.check_health()
        if health.overall_status == HealthStatus.HEALTHY:
            self.logger.info("✅ ELK stack already running and healthy")
            return
        
        # Start containers
        self.logger.info("🐳 Starting ELK containers...")
        result = await self.subprocess_runner.run_command([
            "docker-compose", "-f", docker_compose_path.name, "up", "-d"
        ], cwd=docker_compose_path.parent)
        
        if not result.success:
            raise ELKError(f"Failed to start containers: {result.stderr}")
        
        # Wait for services to be healthy
        await self._wait_for_health()
        
        # Apply ELK configuration
        await self._apply_elk_config(elk_config_path)
        
        self.logger.info("✅ ELK stack initialized successfully")
        self.logger.info("   📊 Elasticsearch: http://localhost:9200")
        self.logger.info("   📈 Kibana: http://localhost:5601")
    
    async def _wait_for_health(self, max_attempts: int = 180) -> None:
        """Wait for ELK services to become healthy"""
        
        self.logger.info("⏳ Waiting for ELK services to be ready...")
        
        for attempt in range(max_attempts):
            health = await self.check_health()
            if health.overall_status == HealthStatus.HEALTHY:
                self.logger.info("✅ ELK stack is healthy")
                return
            
            if attempt % 12 == 0:  # Log every minute
                self.logger.info(f"   Waiting for ELK... ({attempt + 1}/{max_attempts})")
            
            await asyncio.sleep(5)
        
        raise ELKError("ELK stack failed to become healthy after 15 minutes")
    
    # Helper methods
    
    def _get_log_file_path(self, name: str) -> Path:
        """Get log file path for streamer from registry"""
        return self.streamer_manager.get_log_file_path(name)
    
    async def _check_containers_exist(self) -> bool:
        """Check if ELK containers exist"""
        result = await self.subprocess_runner.run_command([
            "docker", "ps", "-a", "--filter", "name=paic-elastic", "--format", "{{.Names}}"
        ])
        return "paic-elastic" in result.stdout
    
    async def _check_containers_running(self) -> bool:
        """Check if ELK containers are running"""
        result = await self.subprocess_runner.run_command([
            "docker", "ps", "--filter", "name=paic-elastic", "--format", "{{.Names}}"
        ])
        return "paic-elastic" in result.stdout
    
    async def _check_elasticsearch_health(self) -> tuple[bool, Optional[str]]:
        """Check Elasticsearch health and return (healthy, version)"""
        try:
            # Check cluster health - HTTPClient.get() returns JSON directly
            health_data = await self.http_client.get("http://localhost:9200/_cluster/health")
            status = health_data.get("status")
            healthy = status in ["green", "yellow"]

            # Get version
            version = None
            try:
                version_data = await self.http_client.get("http://localhost:9200")
                version = version_data.get("version", {}).get("number")
            except Exception:
                pass  # Version is optional

            return healthy, version

        except Exception as e:
            self.logger.debug(f"ES health check failed: {e}")

        return False, None
    
    async def _check_kibana_health(self) -> bool:
        """Check Kibana health"""
        try:
            # HTTPClient.get() returns JSON directly, no need to check status_code
            status_data = await self.http_client.get("http://localhost:5601/api/status")
            overall = status_data.get("status", {}).get("overall", {})
            return overall.get("level") == "available"

        except Exception as e:
            self.logger.debug(f"Kibana health check failed: {e}")

        return False
    
    async def _get_index_stats(self, connection_profile: str) -> tuple[Optional[int], Optional[str]]:
        """Get Elasticsearch index statistics for connection profile"""
        try:
            index_pattern = f"paic-logs-{connection_profile}*"

            # Get document count
            doc_count = None
            try:
                count_data = await self.http_client.get(f"http://localhost:9200/{index_pattern}/_count")
                if count_data:
                    doc_count = count_data.get("count", 0)
            except Exception:
                pass

            # Get index size using JSON format
            index_size = None
            try:
                indices_response = await self.http_client.get(f"http://localhost:9200/_cat/indices/{index_pattern}?format=json")
                if indices_response and isinstance(indices_response, list):
                    # Parse store.size field which comes as "123kb", "45mb", etc.
                    total_bytes = 0
                    for idx in indices_response:
                        size_str = idx.get('store.size', '0b')
                        if size_str and size_str != '-':
                            # Extract number and unit
                            import re
                            match = re.match(r'(\d+(?:\.\d+)?)([kmgt]?b)', size_str.lower())
                            if match:
                                num, unit = match.groups()
                                num = float(num)
                                if unit == 'kb':
                                    total_bytes += int(num * 1024)
                                elif unit == 'mb':
                                    total_bytes += int(num * 1024 * 1024)
                                elif unit == 'gb':
                                    total_bytes += int(num * 1024 * 1024 * 1024)
                                elif unit == 'tb':
                                    total_bytes += int(num * 1024 * 1024 * 1024 * 1024)
                                else:  # 'b'
                                    total_bytes += int(num)

                    # Convert to human readable
                    if total_bytes >= 1024**3:
                        index_size = f"{total_bytes / 1024**3:.1f}GB"
                    elif total_bytes >= 1024**2:
                        index_size = f"{total_bytes / 1024**2:.1f}MB"
                    elif total_bytes >= 1024:
                        index_size = f"{total_bytes / 1024:.1f}KB"
                    else:
                        index_size = f"{total_bytes}B"
            except Exception:
                pass

            return doc_count, index_size
            
        except Exception as e:
            self.logger.debug(f"Failed to get index stats for '{connection_profile}': {e}")
            return None, None
    
    # PUBLIC APIs (called by CLI) - Additional methods
    
    async def start_streamer(self, name: str, connection_profile: str, config: ELKConfig) -> ProcessInfo:
        """Start log streamer with given name using connection profile (replace any existing)"""
        
        # Check for existing streamer (running or stopped)
        existing_entry = self.streamer_manager.get_streamer(name)
        
        if existing_entry:
            if existing_entry.status == "running":
                self.logger.info(f"⚠️  Replacing running streamer '{name}' (PID {existing_entry.pid})")
                await self.stop_streamer(name)
            elif existing_entry.status == "stopped":
                # Check if config changed
                old_components = set(existing_entry.components)
                new_components = set(config.component.split(','))
                old_log_level = existing_entry.log_level
                new_connection = existing_entry.connection_profile

                config_changed = (old_components != new_components or
                                old_log_level != config.log_level or
                                new_connection != connection_profile)

                if config_changed:
                    self.logger.info(f"⚠️  Configuration changed for '{name}'")
                    self.logger.info(f"   Previous: conn={new_connection}, components={sorted(old_components)}, log_level={old_log_level}")
                    self.logger.info(f"   New: conn={connection_profile}, components={sorted(new_components)}, log_level={config.log_level}")
                else:
                    self.logger.info(f"🔄 Restarting stopped streamer '{name}'")

            # Always replace existing entry (running or stopped)
        else:
            self.logger.info(f"🚀 Starting new streamer '{name}' using connection '{connection_profile}'")
        
        # Verify Elasticsearch connectivity first (adapted from original)
        await self._verify_elasticsearch_connection(config.elasticsearch_url)
        
        # Check if we need to create deferred data views (first streamer start)
        await self._handle_deferred_data_views()

        # Get log file path
        log_file = self._get_log_file_path(name)

        # Create modernized streamer command (uses PAICLogService instead of Frodo)
        import sys

        # Build command arguments for modernized log streamer
        streamer_args = [
            "--profile-name", connection_profile,  # Use connection profile for PAIC credentials
            "--source", config.component,
            "--level", str(config.log_level),
            "--elasticsearch-url", config.elasticsearch_url,
            "--batch-size", str(config.batch_size),
            "--flush-interval", str(config.flush_interval),
            "--template-name", config.template_name,
            "--log-file", str(log_file),
        ]

        if config.verbose:
            streamer_args.append("--verbose")

        # Execute modernized streamer module with current Python environment
        streamer_cmd = [sys.executable, "-m", "pctl.services.elk.log_streamer"] + streamer_args

        # Start background process (no PID file needed, we use registry)
        pid = self.subprocess_runner.start_background_process_simple(
            streamer_cmd, log_file
        )

        # Register in streamer manager (updated for new arguments)
        self.streamer_manager.register_streamer(
            name=name,
            connection_profile=connection_profile,
            pid=pid,
            components=config.component.split(','),
            log_level=config.log_level,
            elasticsearch_url=config.elasticsearch_url,
            batch_size=config.batch_size,
            flush_interval=config.flush_interval
        )
        
        self.logger.info(f"🚀 Started streamer '{name}' using connection '{connection_profile}' (PID {pid})")
        self.logger.info(f"   📝 Logs: {log_file}")
        
        return ProcessInfo(
            pid=pid,
            log_file=str(log_file),
            pid_file=None,  # No longer using PID files
            environment=name  # Use name as identifier
        )
    
    async def stop_streamer(self, name: str) -> bool:
        """Stop log streamer by name"""
        
        status = await self.get_status(name)
        if not status.process_running:
            self.logger.warning(f"Streamer '{name}' not running")
            return False
        
        # Stop process
        success = self.subprocess_runner.stop_process_by_pid(status.pid)
        
        # Mark as stopped in registry (keep entry)
        self.streamer_manager.stop_streamer(name)
        
        if success:
            self.logger.info(f"✅ Stopped streamer '{name}'")
        else:
            self.logger.error(f"❌ Failed to stop streamer '{name}'")
        
        return success
    
    async def stop_all_streamers(self) -> int:
        """Stop all running streamers"""
        
        statuses = await self.get_all_statuses()
        stopped_count = 0
        
        for status in statuses:
            if status.process_running:
                success = await self.stop_streamer(status.environment)  # environment field contains the name
                if success:
                    stopped_count += 1
        
        return stopped_count
    
    async def clean_environment_data(self, connection_profile: str) -> None:
        """Clean data for connection profile while keeping streamers running"""
        
        try:
            # First, get all indices matching the pattern
            cat_response = await self.http_client.get_response(f"http://localhost:9200/_cat/indices/paic-logs-{connection_profile}*?format=json")

            if cat_response.is_success():
                indices_data = cat_response.json()
                indices_to_delete = [idx['index'] for idx in indices_data]

                if not indices_to_delete:
                    self.logger.info(f"🧹 No data found for '{connection_profile}' (already clean)")
                    return

                # Delete each index individually
                deleted_count = 0
                for index_name in indices_to_delete:
                    delete_response = await self.http_client.delete_response(f"http://localhost:9200/{index_name}")

                    if delete_response.status_code in [200, 404]:  # 404 means already deleted
                        deleted_count += 1
                    else:
                        self.logger.warning(f"Failed to delete index {index_name}: HTTP {delete_response.status_code}")

                if deleted_count > 0:
                    self.logger.info(f"🧹 Cleaned {deleted_count} indices for '{connection_profile}'")
                else:
                    raise ELKError(f"Failed to delete any indices for '{connection_profile}'")

            elif cat_response.status_code == 404:
                self.logger.info(f"🧹 No data found for '{connection_profile}' (already clean)")
            else:
                raise ELKError(f"Failed to list indices for '{connection_profile}': HTTP {cat_response.status_code}")

        except Exception as e:
            raise ELKError(f"Failed to clean data for '{connection_profile}': {e}")
    
    async def purge_streamer(self, name: str) -> None:
        """Purge streamer completely (stop + delete data for its connection)"""
        
        # Get streamer entry to find connection profile
        entry = self.streamer_manager.get_streamer(name)
        if not entry:
            raise ELKError(f"Streamer '{name}' not found")

        # Stop streamer first
        await self.stop_streamer(name)

        # Clean data for the connection profile
        await self.clean_environment_data(entry.connection_profile)

        # Remove from registry completely
        self.streamer_manager.unregister_streamer(name)

        self.logger.info(f"💪 Purged streamer '{name}' (connection: '{entry.connection_profile}') completely")
    
    async def stop_containers(self) -> None:
        """Stop ELK containers"""
        
        platform_config = self.platform_detector.detect_platform()
        docker_compose_path, _ = self.platform_detector.get_config_files(self.base_config_path)
        
        result = await self.subprocess_runner.run_command([
            "docker-compose", "-f", docker_compose_path.name, "down"
        ], cwd=docker_compose_path.parent)
        
        if result.success:
            self.logger.info("🛑 Stopped ELK containers")
        else:
            raise ELKError(f"Failed to stop containers: {result.stderr}")
    
    async def remove_containers(self) -> None:
        """Remove ELK containers and volumes (deletes data)"""
        
        # Stop all streamers first
        await self.stop_all_streamers()
        
        docker_compose_path, _ = self.platform_detector.get_config_files(self.base_config_path)
        
        result = await self.subprocess_runner.run_command([
            "docker-compose", "-f", docker_compose_path.name, "down", "-v"
        ], cwd=docker_compose_path.parent)
        
        if result.success:
            # Clear all streamers from registry (down = complete removal)
            cleared_count = self.streamer_manager.clear_all_streamers()
            if cleared_count > 0:
                self.logger.info(f"🧹 Cleared {cleared_count} streamers from registry")
            self.logger.info("💥 Removed ELK containers and volumes")
        else:
            raise ELKError(f"Failed to remove containers: {result.stderr}")
    
    async def _verify_elasticsearch_connection(self, elasticsearch_url: str) -> None:
        """Verify Elasticsearch connectivity (adapted from original)"""
        try:
            # HTTPClient.get() returns JSON directly and raises exception if not 200
            es_info = await self.http_client.get(elasticsearch_url.rstrip('/'))
            version = es_info.get("version", {}).get("number", "unknown")
            self.logger.info(f"✅ Elasticsearch connected (v{version})")

        except Exception as e:
            raise ELKError(f"Cannot connect to Elasticsearch: {e}")
    
    async def _apply_elk_config(self, elk_config_path: Path) -> None:
        """Apply ELK configuration from YAML (templates, policies, data views)"""
        self.logger.info("🔧 Setting up ELK configuration from YAML...")
        
        if not elk_config_path.exists():
            self.logger.warning(f"⚠️  ELK config file not found: {elk_config_path}")
            self.logger.warning("   Skipping ELK configuration - using default settings")
            return
        
        try:
            # Parse YAML configuration
            with open(elk_config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            self.logger.info(f"📋 Loading configuration from: {elk_config_path.name}")
            
            # Apply configurations in order
            await self._apply_lifecycle_policies(config.get('lifecycle_policies', {}))
            await self._apply_index_templates(config.get('index_templates', {}))
            
            # Handle data view creation strategy
            bootstrap_config = config.get('bootstrap', {})
            data_view_strategy = bootstrap_config.get('data_view_creation', 'immediate')
            
            if data_view_strategy == 'immediate':
                await self._apply_kibana_data_views(config.get('kibana_data_views', {}))
            else:
                self.logger.info("📈 Data view creation deferred until first streamer starts")
            
            self.logger.info("✅ ELK configuration setup complete!")
            
        except Exception as e:
            self.logger.warning(f"⚠️  ELK configuration setup failed: {e}")
            # Don't fail initialization if config setup fails
    
    async def _apply_lifecycle_policies(self, policies_config: Dict[str, Any]) -> None:
        """Apply lifecycle policies from YAML config"""
        
        if not policies_config:
            self.logger.info("📋 No lifecycle policies to apply")
            return
            
        self.logger.info("📋 Creating lifecycle policies from config...")
        
        for policy_name, policy_config in policies_config.items():
            try:
                # Build the policy payload
                policy_payload = {
                    "policy": {
                        "phases": policy_config.get('phases', {})
                    }
                }
                
                response = await self.http_client.put_response(
                    f"http://localhost:9200/_ilm/policy/{policy_name}",
                    headers={"Content-Type": "application/json"},
                    json=policy_payload
                )

                if response.is_success() and response.json().get("acknowledged", False):
                    phases = policy_config.get('phases', {})
                    hot_phase = phases.get('hot', {}).get('actions', {}).get('rollover', {})
                    delete_phase = phases.get('delete', {})

                    self.logger.info(f"✅ Lifecycle policy '{policy_name}' created")
                    if hot_phase:
                        self.logger.info(f"   🔄 Rollover: {hot_phase.get('max_size', 'N/A')}, {hot_phase.get('max_age', 'N/A')}")
                    if delete_phase:
                        self.logger.info(f"   🗑️  Delete: After {delete_phase.get('min_age', 'N/A')}")
                else:
                    self.logger.warning(f"⚠️  Failed to create lifecycle policy '{policy_name}': HTTP {response.status_code}")
                    
            except Exception as e:
                self.logger.warning(f"⚠️  Failed to create lifecycle policy '{policy_name}': {e}")
    
    async def _apply_index_templates(self, templates_config: Dict[str, Any]) -> None:
        """Apply index templates from YAML config"""
        
        if not templates_config:
            self.logger.info("📊 No index templates to apply")
            return
            
        self.logger.info("📊 Creating index templates from config...")
        
        for template_name, template_config in templates_config.items():
            try:
                # Build the template payload directly from config
                template_payload = {
                    "index_patterns": template_config.get('index_patterns', []),
                    "template": template_config.get('template', {}),
                    "priority": template_config.get('priority', 500),
                    "version": template_config.get('version', 1),
                    "_meta": template_config.get('_meta', {})
                }
                
                response = await self.http_client.put_response(
                    f"http://localhost:9200/_index_template/{template_name}",
                    headers={"Content-Type": "application/json"},
                    json=template_payload
                )

                if response.is_success() and response.json().get("acknowledged", False):
                    priority = template_config.get('priority', 500)
                    patterns = template_config.get('index_patterns', [])
                    self.logger.info(f"✅ Index template '{template_name}' created (priority: {priority})")
                    self.logger.info(f"   📋 Patterns: {', '.join(patterns)}")
                else:
                    self.logger.warning(f"⚠️  Failed to create index template '{template_name}': HTTP {response.status_code}")
                    
            except Exception as e:
                self.logger.warning(f"⚠️  Failed to create index template '{template_name}': {e}")
    
    async def _apply_kibana_data_views(self, data_views_config: Dict[str, Any]) -> None:
        """Apply Kibana data views from YAML config"""
        
        if not data_views_config:
            self.logger.info("📈 No Kibana data views to apply")
            return
            
        self.logger.info("📈 Creating Kibana data views from config...")
        
        for view_id, view_config in data_views_config.items():
            try:
                # Build the data view payload from config
                dataview_payload = {
                    "data_view": {
                        "title": view_config.get('title', ''),
                        "name": view_config.get('name', ''),
                        "timeFieldName": view_config.get('timeFieldName', '@timestamp')
                    }
                }
                
                response = await self.http_client.post_response(
                    "http://localhost:5601/api/data_views/data_view",
                    headers={
                        "Content-Type": "application/json",
                        "kbn-xsrf": "true"
                    },
                    json=dataview_payload
                )

                if response.status_code in [200, 201] and "data_view" in response.text:
                    view_name = view_config.get('name', view_id)
                    view_title = view_config.get('title', '')
                    self.logger.info(f"✅ Kibana data view '{view_name}' created")
                    self.logger.info(f"   📋 Index pattern: {view_title}")
                    self.logger.info(f"   📈 Access via: http://localhost:5601 → Analytics → Discover")
                else:
                    self.logger.warning(f"⚠️  Failed to create Kibana data view '{view_id}' (Kibana may not be ready yet)")
                self.logger.debug(f"Response: {response.text}")
                    
            except Exception as e:
                self.logger.warning(f"⚠️  Failed to create Kibana data view '{view_id}': {e}")
    
    async def _handle_deferred_data_views(self) -> None:
        """Handle deferred data view creation when first streamer starts"""
        
        # Get the platform-specific config path
        platform_info = self.platform_detector.detect_platform()
        elk_config_path = self.base_config_path / platform_info.elk_config_file
        
        if not elk_config_path.exists():
            return
        
        try:
            with open(elk_config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            bootstrap_config = config.get('bootstrap', {})
            data_view_strategy = bootstrap_config.get('data_view_creation', 'immediate')
            
            if data_view_strategy == 'delayed':
                # Check if any data views exist already
                data_views_config = config.get('kibana_data_views', {})
                if data_views_config:
                    # Check if data views already exist
                    existing_views = await self._check_existing_data_views(list(data_views_config.keys()))
                    if not existing_views:
                        self.logger.info("📈 Creating deferred Kibana data views (first streamer start)...")
                        await self._apply_kibana_data_views(data_views_config)
                        # Add a delay and refresh to ensure field detection works
                        await asyncio.sleep(5)  # Give streamer time to index some data
                        await self._refresh_data_view_fields(data_views_config)
                        
        except Exception as e:
            self.logger.warning(f"⚠️  Failed to handle deferred data views: {e}")
    
    async def _check_existing_data_views(self, view_names: List[str]) -> bool:
        """Check if any data views with the given names already exist"""
        
        try:
            response = await self.http_client.get_response(
                "http://localhost:5601/api/data_views",
                headers={"kbn-xsrf": "true"}
            )

            if response.is_success():
                data_views = response.json()
                existing_names = {dv.get('name', '') for dv in data_views.get('data_view', [])}
                return any(name in existing_names for name in view_names)
            
        except Exception as e:
            self.logger.debug(f"Failed to check existing data views: {e}")
        
        return False
    
    async def _refresh_data_view_fields(self, data_views_config: Dict[str, Any]) -> None:
        """Refresh data view fields after data has been indexed"""
        
        for view_id, view_config in data_views_config.items():
            try:
                # Get existing data views to find the ID
                response = await self.http_client.get_response(
                    "http://localhost:5601/api/data_views",
                    headers={"kbn-xsrf": "true"}
                )

                if response.is_success():
                    data_views = response.json()
                    view_name = view_config.get('name', view_id)

                    # Find our data view
                    for dv in data_views.get('data_view', []):
                        if dv.get('name') == view_name:
                            data_view_id = dv.get('id')

                            # Refresh fields
                            refresh_response = await self.http_client.post_response(
                                f"http://localhost:5601/api/data_views/data_view/{data_view_id}/fields",
                                headers={
                                    "Content-Type": "application/json",
                                    "kbn-xsrf": "true"
                                },
                                json={}
                            )

                            if refresh_response.is_success():
                                self.logger.info(f"🔄 Refreshed fields for data view '{view_name}'")
                            break
                            
            except Exception as e:
                self.logger.debug(f"Failed to refresh data view fields for '{view_id}': {e}")