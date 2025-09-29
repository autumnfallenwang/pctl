"""
PAIC Log Service - Internal API for PAIC log streaming operations
Part of the conn domain but separate from profile management
Follows three-layer architecture: Service Layer for business logic and cross-service coordination
"""

import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator
from loguru import logger

from ...core.conn.conn_manager import ConnectionManager
from ...core.conn.paic_api import PAICLogAPI, PAICLogStreamer
from ...core.conn.log_models import LogLevelResolver, NoiseFilter
from ...core.exceptions import ServiceError


class PAICLogService:
    """
    Service layer for PAIC log operations

    Service Layer Rules (from three-layer architecture):
    - Business logic, workflows, cross-service coordination
    - Access: core/conn/* (own domain), services/* (other services)
    - Communication: JSON/dict for cross-service calls (clean contracts)

    Domain Boundary: Part of conn domain, only accessible by other services
    """

    def __init__(self):
        self.logger = logger
        self.connection_manager = ConnectionManager()
        # PAIC API operations (internal to conn domain)
        self.paic_api = PAICLogAPI()
        self.paic_streamer = PAICLogStreamer(self.paic_api)

    async def stream_logs(
        self,
        profile_name: str,
        source: str,
        level: int = 2,  # Default to INFO level (matching ELK default)
        txid: Optional[str] = None,
        use_default_noise_filter: bool = True
    ) -> AsyncIterator[str]:
        """
        Stream logs from PAIC API (for ELK service and future log commands)

        Args:
            profile_name: Connection profile to use
            source: Log source(s) to stream (e.g., "idm-core")
            level: Log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL)
            txid: Optional transaction ID filter
            use_default_noise_filter: Whether to apply default noise filtering

        Yields:
            JSON strings of filtered log events (matching Frodo output format)
        """
        try:
            # Get profile from connection manager
            profile = self.connection_manager.get_profile(profile_name)
            if not profile:
                raise ServiceError(f"Profile '{profile_name}' not found")

            if not profile.has_log_credentials():
                raise ServiceError(f"Profile '{profile_name}' does not have log API credentials configured")

            # Convert numeric level to string array (matching Frodo's level resolution)
            levels = LogLevelResolver.resolve_level(level)

            # Get noise filter
            noise_filter = NoiseFilter.get_default_noise_filter() if use_default_noise_filter else []

            # Start streaming (matching Frodo's tailLogs behavior)
            async for log_json in self.paic_streamer.stream_logs(
                profile=profile,
                source=source,
                levels=levels,
                txid=txid,
                noise_filter=noise_filter
            ):
                yield log_json

        except Exception as e:
            self.logger.error(f"Failed to stream logs for profile {profile_name}: {e}")
            # Yield error as JSON (matching Frodo's error handling)
            yield f'{{"error": "Stream logs error: {str(e)}"}}'

    async def get_log_sources(self, profile_name: str) -> Dict[str, Any]:
        """
        Get available log sources for a profile

        Args:
            profile_name: Connection profile to use

        Returns:
            Dict with sources list for service communication
        """
        try:
            # Get profile from connection manager
            profile = self.connection_manager.get_profile(profile_name)
            if not profile:
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found"
                }

            if not profile.has_log_credentials():
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' does not have log API credentials configured"
                }

            # Get sources from PAIC API
            sources = await self.paic_api.get_log_sources(profile)

            return {
                "success": True,
                "sources": sources
            }

        except Exception as e:
            self.logger.error(f"Failed to get log sources for profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def validate_log_credentials(self, profile_name: str) -> Dict[str, Any]:
        """
        Validate log API credentials for a profile

        Args:
            profile_name: Connection profile to test

        Returns:
            Dict with validation result for service communication
        """
        try:
            # Get profile from connection manager
            profile = self.connection_manager.get_profile(profile_name)
            if not profile:
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found"
                }

            if not profile.has_log_credentials():
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' does not have log API credentials configured"
                }

            # Test credentials by getting log sources
            sources = await self.paic_api.get_log_sources(profile)

            return {
                "success": True,
                "message": f"Log credentials validated for profile '{profile_name}'",
                "sources_count": len(sources)
            }

        except Exception as e:
            self.logger.error(f"Failed to validate log credentials for profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def fetch_historical_logs(
        self,
        profile_name: str,
        source: str,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        level: int = 2,
        txid: Optional[str] = None,
        query_filter: Optional[str] = None,
        use_default_noise_filter: bool = True
    ) -> Dict[str, Any]:
        """
        Fetch historical logs from PAIC API (for future log search commands)

        Args:
            profile_name: Connection profile to use
            source: Log source(s) to search
            start_ts: Start timestamp for historical search
            end_ts: End timestamp for historical search
            level: Log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL)
            txid: Optional transaction ID filter
            query_filter: Optional query filter
            use_default_noise_filter: Whether to apply default noise filtering

        Returns:
            Dict with log events for service communication
        """
        try:
            # Get profile from connection manager
            profile = self.connection_manager.get_profile(profile_name)
            if not profile:
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found"
                }

            if not profile.has_log_credentials():
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' does not have log API credentials configured"
                }

            # Convert numeric level to string array
            levels = LogLevelResolver.resolve_level(level)

            # Get noise filter
            noise_filter = NoiseFilter.get_default_noise_filter() if use_default_noise_filter else []

            # Fetch logs from PAIC API
            logs_result = await self.paic_api.fetch_logs(
                profile=profile,
                source=source,
                start_ts=start_ts,
                end_ts=end_ts,
                txid=txid,
                query_filter=query_filter
            )

            # Apply filtering (matching Frodo's behavior)
            filtered_logs = []
            if logs_result.result:
                for log_event in logs_result.result:
                    if self.paic_streamer._should_include_log(log_event, levels, txid, noise_filter):
                        # Convert to JSON string (matching stream format)
                        log_json = self.paic_streamer._log_event_to_json(log_event)
                        filtered_logs.append(log_json)

            return {
                "success": True,
                "logs": filtered_logs,
                "total_logs": len(filtered_logs),
                "has_more": bool(logs_result.pagedResultsCookie),
                "cookie": logs_result.pagedResultsCookie
            }

        except Exception as e:
            self.logger.error(f"Failed to fetch historical logs for profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_supported_log_levels(self) -> Dict[str, Any]:
        """
        Get supported log levels and their mappings

        Returns:
            Dict with log level information for CLI help
        """
        return {
            "success": True,
            "levels": {
                "1": "ERROR (SEVERE, ERROR, FATAL)",
                "2": "INFO (SEVERE through INFO)",
                "3": "DEBUG (SEVERE through DEBUG, FINE, FINER, FINEST)",
                "4": "ALL (All log levels)"
            },
            "default": 2,
            "description": "Log levels follow Frodo's behavior - higher numbers include lower levels"
        }

    def get_default_noise_filter_info(self) -> Dict[str, Any]:
        """
        Get information about default noise filtering

        Returns:
            Dict with noise filter information for CLI help
        """
        noise_filter = NoiseFilter.get_default_noise_filter()

        return {
            "success": True,
            "filter_count": len(noise_filter),
            "description": "Default noise filter removes verbose AM/IDM internal logging",
            "categories": [
                "OpenAM authentication internals",
                "Service management operations",
                "LDAP connection pooling",
                "SAML XML processing",
                "OAuth2 provider settings"
            ]
        }