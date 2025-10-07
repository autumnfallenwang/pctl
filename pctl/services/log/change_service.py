"""
Service layer for configuration change tracking.

This module provides business logic for fetching and analyzing
configuration changes from PAIC audit logs.
"""

from typing import Any, Dict, Optional
from loguru import logger

from ...core.log.change_models import ConfigChangeEvent
from ..conn.log_service import PAICLogService


class ChangeService:
    """
    Service for tracking configuration changes.

    Fetches historical logs and parses them into structured change events.
    """

    # Resource type to log source mapping
    RESOURCE_MAPPINGS = {
        'endpoint': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "endpoint/{name}"'
        },
        'journey': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "journey/{name}"'
        },
        'script': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "script/{name}"'
        }
    }

    def __init__(self):
        """Initialize ChangeService."""
        self.logger = logger
        self.log_service = PAICLogService()

    async def fetch_changes(
        self,
        profile_name: str,
        resource_type: str,
        resource_name: str,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch configuration changes for a specific resource.

        Args:
            profile_name: Connection profile name
            resource_type: Type of resource (endpoint, journey, script)
            resource_name: Name of the resource
            start_ts: Start timestamp (ISO-8601 format, optional)
            end_ts: End timestamp (ISO-8601 format, optional)

        Returns:
            Dictionary with:
                - success: bool
                - total_changes: int
                - resource_type: str
                - resource_name: str
                - time_range: dict
                - changes: List[dict]  # ConfigChangeEvent.to_dict()

        Raises:
            ValueError: If resource_type is not supported
        """
        # Validate resource type
        if resource_type not in self.RESOURCE_MAPPINGS:
            raise ValueError(
                f"Unsupported resource type: {resource_type}. "
                f"Supported types: {', '.join(self.RESOURCE_MAPPINGS.keys())}"
            )

        # Get resource mapping
        mapping = self.RESOURCE_MAPPINGS[resource_type]
        source = mapping['source']
        query_filter = mapping['query_template'].format(name=resource_name)

        self.logger.info(
            f"Fetching {resource_type} changes for '{resource_name}' "
            f"from profile '{profile_name}'"
        )

        # Fetch raw logs using PAICLogService (other params use defaults)
        result = await self.log_service.fetch_historical_logs(
            profile_name=profile_name,
            source=source,
            start_ts=start_ts,
            end_ts=end_ts,
            query_filter=query_filter
        )

        # Parse raw logs into ConfigChangeEvent objects
        changes = []
        for log_entry in result["logs"]:
            try:
                change_event = ConfigChangeEvent.from_log_entry(log_entry, resource_type)
                changes.append(change_event.to_dict())
            except Exception as e:
                self.logger.warning(
                    f"Failed to parse log entry {log_entry.get('timestamp', 'unknown')}: {e}"
                )
                continue

        self.logger.info(f"Parsed {len(changes)} change events")

        # Return clean dict for CLI
        return {
            "success": True,
            "total_changes": len(changes),
            "resource_type": resource_type,
            "resource_name": resource_name,
            "time_range": result.get("time_range", {}),
            "changes": changes
        }
