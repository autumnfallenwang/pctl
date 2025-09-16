"""
Core configuration utilities for pctl
Handles YAML loading, validation, and cross-command config sharing
"""

from pathlib import Path
from typing import Dict, Any
import yaml
from loguru import logger
from .exceptions import ConfigError


class PathConfig:
    """Centralized path configuration for pctl"""

    @staticmethod
    def get_pctl_home() -> Path:
        """Get pctl home directory: ~/.pctl/"""
        return Path.home() / ".pctl"

    @staticmethod
    def get_connections_file() -> Path:
        """Get connection profiles file: ~/.pctl/connections.json"""
        return PathConfig.get_pctl_home() / "connections.json"

    @staticmethod
    def get_streamers_file() -> Path:
        """Get streamers registry file: ~/.pctl/streamers.json"""
        return PathConfig.get_pctl_home() / "streamers.json"

    @staticmethod
    def get_logs_dir() -> Path:
        """Get logs directory: ~/.pctl/logs/"""
        return PathConfig.get_pctl_home() / "logs"

    @staticmethod
    def ensure_pctl_dirs() -> None:
        """Ensure all pctl directories exist"""
        PathConfig.get_pctl_home().mkdir(parents=True, exist_ok=True)
        PathConfig.get_logs_dir().mkdir(parents=True, exist_ok=True)


class ConfigLoader:
    """Core utility for configuration loading and parsing"""
    
    def __init__(self):
        self.logger = logger
    
    async def load_yaml(self, config_path: str | Path) -> Dict[str, Any]:
        """Load and parse YAML configuration file"""
        try:
            config_path = Path(config_path)
            if not config_path.exists():
                raise ConfigError(f"Config file not found: {config_path}")
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            self.logger.info(f"Loaded config from {config_path}")
            return config
            
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {config_path}: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config {config_path}: {e}")
    
    async def validate_config_keys(self, config: Dict[str, Any], required_keys: list[str]) -> None:
        """Validate required keys exist in config"""
        missing = [key for key in required_keys if key not in config]
        if missing:
            raise ConfigError(f"Missing required config keys: {missing}")
    
    async def get_config_path(self, config_type: str, config_name: str) -> Path:
        """Get standardized config path"""
        base_path = Path("pctl/configs") / config_type / config_name
        if not base_path.suffix:
            base_path = base_path.with_suffix('.yaml')
        return base_path