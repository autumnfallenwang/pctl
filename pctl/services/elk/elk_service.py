"""
ELK Service - Internal API for ELK stack management
"""

import asyncio
import json
import yaml
import httpx
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

from ...core.elk.elk_models import ELKHealth, StreamerStatus, ProcessInfo, ELKConfig, HealthStatus
from ...core.elk.platform import PlatformDetector
from ...core.subprocess_runner import SubprocessRunner
from ...core.exceptions import ELKError, ServiceError
from ...core.config import ConfigLoader


class ELKService:
    """Service for ELK stack management with internal APIs"""
    
    def __init__(self, config_dir: Optional[str] = None, require_config: bool = True):
        self.logger = logger
        self.subprocess_runner = SubprocessRunner()
        self.platform_detector = PlatformDetector()
        self.config_loader = ConfigLoader()
        
        # Smart config path resolution for deployment
        if require_config:
            self.base_config_path = self._resolve_config_path(config_dir)
            # Logs path - use a deployment-friendly location  
            self.logs_path = self.base_config_path.parent / "logs"
            self.logs_path.mkdir(exist_ok=True)
        else:
            # For commands that don't need config, use simple defaults
            self.base_config_path = None
            self.logs_path = Path.cwd() / "logs"  # Fallback for PID files
            self.logs_path.mkdir(exist_ok=True)
    
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
    
    async def get_status(self, environment: str) -> StreamerStatus:
        """Internal API: Get single environment streamer status"""
        
        pid_file, log_file = self._find_streamer_files(environment)
        
        # Check if process is running
        process_running = False
        pid = None
        
        if pid_file.exists():
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Check if process actually exists
                import os
                os.kill(pid, 0)  # Raises OSError if process doesn't exist
                process_running = True
                
            except (OSError, ValueError):
                # Process not running or invalid PID file
                process_running = False
                pid = None
        
        # Get log file info
        log_file_size = None
        last_activity = None
        
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
                index_doc_count, index_size = await self._get_index_stats(environment)
        except Exception as e:
            self.logger.debug(f"Could not get ES stats for {environment}: {e}")
        
        return StreamerStatus(
            environment=environment,
            process_running=process_running,
            pid=pid,
            log_file_path=str(log_file) if log_file.exists() else None,
            log_file_size=log_file_size,
            last_activity=last_activity,
            index_doc_count=index_doc_count,
            index_size=index_size
        )
    
    async def get_all_statuses(self) -> List[StreamerStatus]:
        """Internal API: Get all environment statuses"""
        
        environments = []
        
        # Find all PID files to determine environments (check both locations)
        for search_path in [Path.cwd(), self.logs_path]:
            for pid_file in search_path.glob("paic_streamer_*.pid"):
                env_name = pid_file.stem.replace("paic_streamer_", "")
                if env_name not in environments:
                    environments.append(env_name)
        
        # Also check for log files without PID files (stopped streamers)
        for search_path in [Path.cwd(), self.logs_path]:
            for log_file in search_path.glob("paic_streamer_*.log"):
                env_name = log_file.stem.replace("paic_streamer_", "")
                if env_name not in environments:
                    environments.append(env_name)
        
        # Get status for each environment
        statuses = []
        for env in environments:
            try:
                status = await self.get_status(env)
                statuses.append(status)
            except Exception as e:
                self.logger.error(f"Failed to get status for {env}: {e}")
        
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
    
    def _get_streamer_files(self, environment: str, log_dir: Optional[Path] = None) -> tuple[Path, Path]:
        """Get PID and log file paths for environment"""
        # Use provided log_dir or default to current working directory
        base_dir = log_dir if log_dir else Path.cwd()
        pid_file = base_dir / f"paic_streamer_{environment}.pid"
        log_file = base_dir / f"paic_streamer_{environment}.log"
        return pid_file, log_file
    
    def _find_streamer_files(self, environment: str) -> tuple[Path, Path]:
        """Find existing PID and log file paths for environment (checks multiple locations)"""
        # Check current directory first (new default)
        cwd_pid = Path.cwd() / f"paic_streamer_{environment}.pid"
        cwd_log = Path.cwd() / f"paic_streamer_{environment}.log"
        
        # Check old location for backward compatibility
        old_pid = self.logs_path / f"paic_streamer_{environment}.pid"
        old_log = self.logs_path / f"paic_streamer_{environment}.log"
        
        # Return the files that exist, preferring current directory
        if cwd_pid.exists() or cwd_log.exists():
            return cwd_pid, cwd_log
        else:
            return old_pid, old_log
    
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
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check cluster health
                health_response = await client.get("http://localhost:9200/_cluster/health")
                
                if health_response.status_code == 200:
                    health_data = health_response.json()
                    status = health_data.get("status")
                    healthy = status in ["green", "yellow"]
                    
                    # Get version
                    version = None
                    try:
                        version_response = await client.get("http://localhost:9200")
                        if version_response.status_code == 200:
                            version_data = version_response.json()
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
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:5601/api/status")
                
                if response.status_code == 200:
                    status_data = response.json()
                    overall = status_data.get("status", {}).get("overall", {})
                    return overall.get("level") == "available"
                
        except Exception as e:
            self.logger.debug(f"Kibana health check failed: {e}")
        
        return False
    
    async def _get_index_stats(self, environment: str) -> tuple[Optional[int], Optional[str]]:
        """Get Elasticsearch index statistics for environment"""
        try:
            index_pattern = f"paic-logs-{environment}*"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get document count
                doc_count = None
                try:
                    count_response = await client.get(f"http://localhost:9200/{index_pattern}/_count")
                    if count_response.status_code == 200:
                        count_data = count_response.json()
                        doc_count = count_data.get("count", 0)
                except Exception:
                    pass
                
                # Get index size
                index_size = None
                try:
                    size_response = await client.get(f"http://localhost:9200/_cat/indices/{index_pattern}?h=store.size&bytes=b")
                    if size_response.status_code == 200 and size_response.text.strip():
                        total_bytes = sum(int(line.strip()) for line in size_response.text.strip().split('\n') if line.strip())
                        # Convert to human readable
                        if total_bytes >= 1024**3:
                            index_size = f"{total_bytes / 1024**3:.1f}GB"
                        elif total_bytes >= 1024**2:
                            index_size = f"{total_bytes / 1024**2:.1f}MB"
                        else:
                            index_size = f"{total_bytes / 1024:.1f}KB"
                except Exception:
                    pass
                
                return doc_count, index_size
            
        except Exception as e:
            self.logger.debug(f"Failed to get index stats for {environment}: {e}")
            return None, None
    
    # PUBLIC APIs (called by CLI) - Additional methods
    
    async def start_streamer(self, environment: str, config: ELKConfig, log_dir: Optional[Path] = None) -> ProcessInfo:
        """Start log streamer for environment"""
        
        # Check if already running
        status = await self.get_status(environment)
        if status.process_running:
            self.logger.info(f"Streamer for {environment} already running (PID {status.pid}), stopping first...")
            await self.stop_streamer(environment)
        
        # Verify Elasticsearch connectivity first (adapted from original)
        await self._verify_elasticsearch_connection(config.elasticsearch_url)
        
        # Check if we need to create deferred data views (first streamer start)
        await self._handle_deferred_data_views()
        
        # Build frodo command (adapted from original streamer)
        frodo_cmd = [
            "frodo", "log", "tail",  # Note: original uses "log" not "logs"
            "-c", config.component,
            "-l", str(config.log_level),
            environment
        ]
        
        # Get file paths
        pid_file, log_file = self._get_streamer_files(environment, log_dir)
        
        # Create streamer command (uses current binary or python module)
        import sys
        
        # Build command arguments for streamer module execution
        streamer_args = [
            "--environment", environment,
            "--elasticsearch-url", config.elasticsearch_url,
            "--batch-size", str(config.batch_size),
            "--flush-interval", str(config.flush_interval),
            "--template-name", config.template_name,
            "--log-file", str(log_file),
            "--pid-file", str(pid_file),
            "--frodo-cmd", " ".join(frodo_cmd),
        ]
        
        if config.verbose:
            streamer_args.append("--verbose")
        
        # Execute streamer module with current Python environment
        streamer_cmd = [sys.executable, "-m", "pctl.core.elk.streamer_process"] + streamer_args
        
        # Start background process
        pid = self.subprocess_runner.start_background_process(
            streamer_cmd, log_file, pid_file
        )
        
        self.logger.info(f"🚀 Started streamer for {environment} (PID {pid})")
        self.logger.info(f"   📝 Logs: {log_file}")
        
        return ProcessInfo(
            pid=pid,
            log_file=str(log_file),
            pid_file=str(pid_file),
            environment=environment
        )
    
    async def stop_streamer(self, environment: str) -> bool:
        """Stop log streamer for environment"""
        
        status = await self.get_status(environment)
        if not status.process_running:
            self.logger.warning(f"Streamer for {environment} not running")
            return False
        
        # Stop process
        success = self.subprocess_runner.stop_process_by_pid(status.pid)
        
        # Clean up PID file
        pid_file, _ = self._find_streamer_files(environment)
        if pid_file.exists():
            pid_file.unlink()
        
        if success:
            self.logger.info(f"✅ Stopped streamer for {environment}")
        else:
            self.logger.error(f"❌ Failed to stop streamer for {environment}")
        
        return success
    
    async def stop_all_streamers(self) -> int:
        """Stop all running streamers"""
        
        statuses = await self.get_all_statuses()
        stopped_count = 0
        
        for status in statuses:
            if status.process_running:
                success = await self.stop_streamer(status.environment)
                if success:
                    stopped_count += 1
        
        return stopped_count
    
    async def clean_environment_data(self, environment: str) -> None:
        """Clean environment data while keeping streamer running"""
        
        index_pattern = f"paic-logs-{environment}*"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(f"http://localhost:9200/{index_pattern}")
                
                if response.status_code in [200, 404]:  # 404 means already deleted
                    self.logger.info(f"🧹 Cleaned data for {environment}")
                else:
                    raise ELKError(f"Failed to clean data for {environment}: HTTP {response.status_code}")
        except httpx.RequestError as e:
            raise ELKError(f"Failed to clean data for {environment}: {e}")
    
    async def purge_environment(self, environment: str) -> None:
        """Purge environment completely (stop + delete)"""
        
        # Stop streamer first
        await self.stop_streamer(environment)
        
        # Clean data
        await self.clean_environment_data(environment)
        
        self.logger.info(f"💥 Purged environment {environment} completely")
    
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
        
        platform_config = self.platform_detector.detect_platform()
        docker_compose_path, _ = self.platform_detector.get_config_files(self.base_config_path)
        
        result = await self.subprocess_runner.run_command([
            "docker-compose", "-f", docker_compose_path.name, "down", "-v"
        ], cwd=docker_compose_path.parent)
        
        if result.success:
            self.logger.info("💥 Removed ELK containers and volumes")
        else:
            raise ELKError(f"Failed to remove containers: {result.stderr}")
    
    async def _verify_elasticsearch_connection(self, elasticsearch_url: str) -> None:
        """Verify Elasticsearch connectivity (adapted from original)"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(elasticsearch_url.rstrip('/'))
                
                if response.status_code == 200:
                    es_info = response.json()
                    version = es_info.get("version", {}).get("number", "unknown")
                    self.logger.info(f"✅ Elasticsearch connected (v{version})")
                else:
                    raise ELKError(f"Elasticsearch not responding: HTTP {response.status_code}")
                    
        except httpx.RequestError as e:
            raise ELKError(f"Elasticsearch not responding: {e}")
        except json.JSONDecodeError:
            raise ELKError(f"Invalid response from Elasticsearch at {elasticsearch_url}")
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
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.put(
                        f"http://localhost:9200/_ilm/policy/{policy_name}",
                        headers={"Content-Type": "application/json"},
                        json=policy_payload
                    )
                    
                    if response.status_code == 200 and response.json().get("acknowledged", False):
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
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.put(
                        f"http://localhost:9200/_index_template/{template_name}",
                        headers={"Content-Type": "application/json"},
                        json=template_payload
                    )
                    
                    if response.status_code == 200 and response.json().get("acknowledged", False):
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
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
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
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "http://localhost:5601/api/data_views",
                    headers={"kbn-xsrf": "true"}
                )
                
                if response.status_code == 200:
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
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        "http://localhost:5601/api/data_views",
                        headers={"kbn-xsrf": "true"}
                    )
                    
                    if response.status_code == 200:
                        data_views = response.json()
                        view_name = view_config.get('name', view_id)
                        
                        # Find our data view
                        for dv in data_views.get('data_view', []):
                            if dv.get('name') == view_name:
                                data_view_id = dv.get('id')
                                
                                # Refresh fields
                                refresh_response = await client.post(
                                    f"http://localhost:5601/api/data_views/data_view/{data_view_id}/fields",
                                    headers={
                                        "Content-Type": "application/json",
                                        "kbn-xsrf": "true"
                                    },
                                    json={}
                                )
                                
                                if refresh_response.status_code == 200:
                                    self.logger.info(f"🔄 Refreshed fields for data view '{view_name}'")
                                break
                            
            except Exception as e:
                self.logger.debug(f"Failed to refresh data view fields for '{view_id}': {e}")