"""
Platform detection and configuration management for ELK stack
"""

import platform
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple
from loguru import logger


@dataclass
class PlatformConfig:
    """Platform-specific configuration"""
    name: str
    docker_compose_file: str
    elk_config_file: str
    
    
class PlatformDetector:
    """Detect platform and select appropriate config files"""
    
    def __init__(self):
        self.logger = logger
    
    def detect_platform(self) -> PlatformConfig:
        """Detect platform and return appropriate config"""
        system = platform.system()
        arch = platform.machine()
        
        self.logger.debug(f"Detected system: {system}, architecture: {arch}")
        
        if system == "Darwin":
            # macOS - check architecture
            if arch == "arm64":
                return PlatformConfig(
                    name="macOS Apple Silicon (M1/M2/M3/M4)",
                    docker_compose_file="docker-compose-mac-arm.yml",
                    elk_config_file="elk_init_config-mac-arm.yaml"
                )
            else:
                return PlatformConfig(
                    name="macOS Intel x64", 
                    docker_compose_file="docker-compose-linux-x64.yml",
                    elk_config_file="elk_init_config-linux-x64.yaml"
                )
        elif system == "Linux":
            return PlatformConfig(
                name="Linux x64",
                docker_compose_file="docker-compose-linux-x64.yml", 
                elk_config_file="elk_init_config-linux-x64.yaml"
            )
        else:
            # Fallback for unknown platforms
            self.logger.warning(f"Unsupported platform: {system} (Linux/macOS recommended)")
            return PlatformConfig(
                name=f"{system} (fallback to x64 config)",
                docker_compose_file="docker-compose-linux-x64.yml",
                elk_config_file="elk_init_config-linux-x64.yaml"
            )
    
    def get_config_files(self, base_path: Path) -> Tuple[Path, Path]:
        """Get full paths to platform-specific config files"""
        config = self.detect_platform()
        
        docker_compose_path = base_path / config.docker_compose_file
        elk_config_path = base_path / config.elk_config_file
        
        # Verify files exist
        if not docker_compose_path.exists():
            raise FileNotFoundError(f"Docker compose file not found: {docker_compose_path}")
        if not elk_config_path.exists():
            raise FileNotFoundError(f"ELK config file not found: {elk_config_path}")
            
        return docker_compose_path, elk_config_path
    
    def check_dependencies(self) -> list[str]:
        """Check for required system dependencies"""
        import shutil
        
        missing_deps = []
        required_commands = ["docker", "docker-compose", "python3", "curl", "frodo"]
        
        for cmd in required_commands:
            if not shutil.which(cmd):
                if cmd == "frodo":
                    missing_deps.append("frodo (Frodo CLI)")
                else:
                    missing_deps.append(cmd)
                    
        return missing_deps