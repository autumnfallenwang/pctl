"""
Connection Service - Internal API for connection profile management
Follows three-layer architecture: Service Layer for business logic and cross-service coordination
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any
from loguru import logger

from ...core.conn.conn_manager import ConnectionManager
from ...core.conn.conn_models import ConnectionProfile
from ...core.config import ConfigLoader
from ...core.exceptions import ServiceError, ConfigError


class ConnectionService:
    """
    Service layer for connection profile operations

    Service Layer Rules (from three-layer architecture):
    - Business logic, workflows, cross-service coordination, user prompting
    - Access: core/* (shared), core/conn/ (own domain), services/* (other services)
    - Communication: JSON/dict for cross-service calls (clean contracts)
    """

    def __init__(self):
        self.logger = logger
        self.connection_manager = ConnectionManager()
        self.config_loader = ConfigLoader()

    def create_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new connection profile with business validation

        Args:
            profile_data: Profile data dict for cross-service communication

        Returns:
            Dict with creation result for service-to-service calls
        """
        try:
            # Create profile object (core layer handles validation)
            profile = ConnectionProfile.from_dict(profile_data)

            # Business logic: Check for name conflicts
            if self.connection_manager.profile_exists(profile.name):
                raise ServiceError(f"Profile '{profile.name}' already exists")

            # Business validation
            issues = self.connection_manager.validate_profile(profile)
            if issues:
                raise ServiceError(f"Profile validation failed: {', '.join(issues)}")

            # Save profile
            self.connection_manager.save_profile(profile)

            self.logger.info(f"Created connection profile: {profile.name}")

            return {
                "success": True,
                "profile_name": profile.name,
                "message": f"Profile '{profile.name}' created successfully"
            }

        except Exception as e:
            self.logger.error(f"Failed to create profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def create_profile_from_config(self, config_path: Path, conn_name: str) -> Dict[str, Any]:
        """Create connection profile from YAML config file"""
        try:
            # Load YAML config (hide async in service layer)
            config_data = asyncio.run(self.config_loader.load_yaml(config_path))

            # Map config fields to profile fields (simple mapping)
            profile_data = {
                "name": conn_name,
                "platform_url": config_data.get("platform"),
                "service_account_id": config_data.get("sa_id"),
                "service_account_jwk": self._resolve_jwk_from_config(config_data, config_path.parent)
            }

            # Add optional fields
            for field in ["log_api_key", "log_api_secret", "admin_username", "admin_password", "description"]:
                if config_data.get(field):
                    profile_data[field] = config_data[field]

            # Create the profile
            return self.create_profile(profile_data)

        except Exception as e:
            self.logger.error(f"Failed to create profile from config: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _resolve_jwk_from_config(self, config_data: dict, config_dir: Path) -> str:
        """Resolve JWK from config - sa_jwk (direct) or sa_jwk_file (file path)"""

        # Direct JWK JSON string
        if "sa_jwk" in config_data:
            jwk_data = config_data["sa_jwk"]
            return jwk_data if isinstance(jwk_data, str) else json.dumps(jwk_data)

        # JWK file path
        if "sa_jwk_file" in config_data:
            jwk_file_path = config_data["sa_jwk_file"]

            # Handle relative paths
            if not Path(jwk_file_path).is_absolute():
                jwk_file_path = config_dir / jwk_file_path
            else:
                jwk_file_path = Path(jwk_file_path)

            if not jwk_file_path.exists():
                raise ConfigError(f"JWK file not found: {jwk_file_path}")

            jwk_content = jwk_file_path.read_text(encoding='utf-8')
            # Validate JSON
            json.loads(jwk_content)
            return jwk_content

        raise ConfigError("No JWK found in config. Provide either 'sa_jwk' or 'sa_jwk_file'")

    def get_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Get connection profile by name

        Args:
            profile_name: Name of the profile to retrieve

        Returns:
            Dict with profile data for cross-service communication
        """
        try:
            profile = self.connection_manager.get_profile(profile_name)

            if not profile:
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found"
                }

            return {
                "success": True,
                "profile": profile.to_dict()
            }

        except Exception as e:
            self.logger.error(f"Failed to get profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def list_profiles(self) -> Dict[str, Any]:
        """
        List all connection profiles

        Returns:
            Dict with profiles list for cross-service communication
        """
        try:
            profiles = self.connection_manager.list_profiles()

            return {
                "success": True,
                "profiles": [profile.to_dict() for profile in profiles],
                "count": len(profiles)
            }

        except Exception as e:
            self.logger.error(f"Failed to list profiles: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Delete connection profile with business logic

        Args:
            profile_name: Name of profile to delete

        Returns:
            Dict with deletion result for cross-service communication
        """
        try:
            # Business logic: Check if profile exists
            if not self.connection_manager.profile_exists(profile_name):
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found"
                }

            # Delete profile
            success = self.connection_manager.remove_profile(profile_name)

            if success:
                self.logger.info(f"Deleted connection profile: {profile_name}")
                return {
                    "success": True,
                    "message": f"Profile '{profile_name}' deleted successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to delete profile '{profile_name}'"
                }

        except Exception as e:
            self.logger.error(f"Failed to delete profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_default_profile(self) -> Dict[str, Any]:
        """
        Get default connection profile with business logic

        Returns:
            Dict with default profile for cross-service communication
        """
        try:
            profile = self.connection_manager.get_default_profile()

            if not profile:
                return {
                    "success": False,
                    "error": "No profiles configured. Create a profile first."
                }

            return {
                "success": True,
                "profile": profile.to_dict()
            }

        except Exception as e:
            self.logger.error(f"Failed to get default profile: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_service_status(self) -> Dict[str, Any]:
        """
        Get connection service status and diagnostics

        Returns:
            Dict with service status for monitoring and debugging
        """
        try:
            # Get connections info from core layer
            connections_info = self.connection_manager.get_connections_info()

            # Get profiles list
            profiles_result = self.list_profiles()

            return {
                "success": True,
                "service": "ConnectionService",
                "connections": connections_info,
                "profiles": profiles_result if profiles_result["success"] else {"error": profiles_result["error"]},
                "default_profile": self.get_default_profile()
            }

        except Exception as e:
            self.logger.error(f"Failed to get service status: {e}")
            return {
                "success": False,
                "error": str(e)
            }