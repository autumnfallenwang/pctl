"""
Connection Profile Manager
JSON-based connection profile management
"""

import json
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from ..config import PathConfig
from ..exceptions import ConfigError
from .conn_models import ConnectionProfile


class ConnectionManager:
    """
    Manages connection profiles in JSON format
    Similar pattern to StreamerRegistry but for connection profiles
    """

    def __init__(self):
        """Initialize connection manager"""
        # Ensure pctl directories exist
        PathConfig.ensure_pctl_dirs()

        self.connections_file = PathConfig.get_connections_file()

        # Initialize empty connections file if doesn't exist
        if not self.connections_file.exists():
            self._write_connections({})

    def _read_connections(self) -> Dict[str, dict]:
        """Safely read connections file"""
        try:
            if not self.connections_file.exists():
                return {}

            content = self.connections_file.read_text(encoding='utf-8')
            return json.loads(content) if content.strip() else {}

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read connections file: {e}")
            return {}

    def _write_connections(self, data: Dict[str, dict], retries: int = 3) -> None:
        """Safely write connections file with atomic operation"""
        for attempt in range(retries):
            try:
                # Write to temporary file first (atomic operation)
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    dir=self.connections_file.parent,
                    delete=False,
                    suffix='.tmp',
                    encoding='utf-8'
                ) as temp_file:
                    json.dump(data, temp_file, indent=2, ensure_ascii=False)
                    temp_file.flush()

                    # Atomic rename (on most filesystems)
                    Path(temp_file.name).rename(self.connections_file)
                    return

            except OSError as e:
                if attempt == retries - 1:
                    logger.error(f"Failed to write connections file after {retries} attempts: {e}")
                    raise ConfigError(f"Could not save connections: {e}")
                else:
                    logger.debug(f"Connections write attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(0.1)  # Brief delay before retry

    def save_profile(self, profile: ConnectionProfile) -> None:
        """Save a connection profile"""
        if not profile.name:
            raise ConfigError("Connection profile name cannot be empty")

        data = self._read_connections()
        data[profile.name] = profile.to_dict()
        self._write_connections(data)

        logger.debug(f"Saved connection profile: {profile.name}")

    def get_profile(self, name: str) -> Optional[ConnectionProfile]:
        """Get a connection profile by name"""
        data = self._read_connections()
        profile_dict = data.get(name)

        if profile_dict:
            try:
                return ConnectionProfile.from_dict(profile_dict)
            except (TypeError, ValueError) as e:
                logger.warning(f"Invalid connection profile for {name}: {e}")
                # Note: Don't auto-remove invalid profiles, let user handle it
                return None

        return None

    def list_profiles(self) -> List[ConnectionProfile]:
        """List all connection profiles"""
        data = self._read_connections()
        profiles = []

        for name, profile_dict in data.items():
            try:
                profiles.append(ConnectionProfile.from_dict(profile_dict))
            except (TypeError, ValueError) as e:
                logger.warning(f"Invalid connection profile for {name}: {e}")
                # Skip invalid profiles but don't remove them

        return profiles

    def list_profile_names(self) -> List[str]:
        """List connection profile names"""
        data = self._read_connections()
        return list(data.keys())

    def remove_profile(self, name: str) -> bool:
        """Remove a connection profile"""
        data = self._read_connections()

        if name in data:
            del data[name]
            self._write_connections(data)
            logger.debug(f"Removed connection profile: {name}")
            return True

        return False

    def profile_exists(self, name: str) -> bool:
        """Check if a profile exists"""
        data = self._read_connections()
        return name in data

    def get_default_profile(self) -> Optional[ConnectionProfile]:
        """
        Get default profile (first available or 'commkentsb2' if it exists)
        This matches current behavior where commkentsb2 is the default environment
        """
        profiles = self.list_profiles()

        if not profiles:
            return None

        # Look for commkentsb2 first (current default)
        for profile in profiles:
            if profile.name == 'commkentsb2':
                return profile

        # Return first available profile
        return profiles[0]

    def validate_profile(self, profile: ConnectionProfile) -> List[str]:
        """
        Validate a connection profile and return list of issues
        Returns empty list if profile is valid
        """
        issues = []

        if not profile.name:
            issues.append("Profile name is required")

        if not profile.platform_url:
            issues.append("Platform URL is required")
        elif not profile.platform_url.startswith(('http://', 'https://')):
            issues.append("Platform URL must start with http:// or https://")

        # Check that at least one authentication method is available
        has_log_creds = profile.has_log_credentials()
        has_service_account = profile.has_service_account_credentials()
        has_admin_creds = profile.has_admin_credentials()

        if not (has_log_creds or has_service_account or has_admin_creds):
            issues.append("Profile must have at least one authentication method (log API keys, service account config, or admin credentials)")

        return issues

    def get_connections_info(self) -> dict:
        """Get connections metadata for debugging"""
        data = self._read_connections()

        return {
            "connections_file": str(self.connections_file),
            "pctl_home": str(PathConfig.get_pctl_home()),
            "total_profiles": len(data),
            "profile_names": list(data.keys()),
            "connections_file_exists": self.connections_file.exists(),
            "pctl_home_exists": PathConfig.get_pctl_home().exists()
        }