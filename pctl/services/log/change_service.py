"""
Service layer for configuration change tracking.

This module provides business logic for fetching and analyzing
configuration changes from PAIC audit logs.
"""

from typing import Any, Dict, Optional
from loguru import logger

from ...core.log.change_models import ConfigChangeEvent
from ...core.exceptions import ServiceError
from ..conn.log_service import PAICLogService
from ..conn.paic_api_service import ScriptAPIService


class ChangeService:
    """
    Service for tracking configuration changes.

    Fetches historical logs and parses them into structured change events.
    """

    # Resource type to log source mapping
    RESOURCE_MAPPINGS = {
        # IDM-Config - Pattern 1: Type/Name (requires name)
        'endpoint': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "endpoint/{name}"',
            'requires_name': True,
            'requires_uuid_lookup': False
        },
        'connector': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "provisioner.openicf/{name}"',
            'requires_name': True,
            'requires_uuid_lookup': False
        },
        'emailTemplate': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "emailTemplate/{name}"',
            'requires_name': True,
            'requires_uuid_lookup': False
        },
        'mapping': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "mapping/{name}"',
            'requires_name': True,
            'requires_uuid_lookup': False
        },

        # IDM-Config - Pattern 2: Type Only (no name needed)
        'access': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "access"',
            'requires_name': False,
            'requires_uuid_lookup': False
        },
        'repo': {
            'source': 'idm-config',
            'query_template': '/payload/objectId eq "repo.ds"',
            'requires_name': False,
            'requires_uuid_lookup': False
        },

        # AM-Config - Pattern 3: LDAP DN with UUID (requires name → UUID lookup)
        'script': {
            'source': 'am-config',
            'query_template': '/payload/objectId co "ou={uuid},ou=scriptConfigurations"',
            'requires_name': True,
            'requires_uuid_lookup': True
        },

        # AM-Config - Pattern 4: LDAP DN with name (requires name)
        'journey': {
            'source': 'am-config',
            'query_template': '/payload/objectId co "ou={name},ou=default,ou=OrganizationConfig,ou=1.0,ou=authenticationTreesService"',
            'requires_name': True,
            'requires_uuid_lookup': False
        },

        # AM-Config - Pattern 5: LDAP DN with entity ID (requires name as entity_id)
        'saml': {
            'source': 'am-config',
            'query_template': '/payload/objectId co "ou={name},ou=default,ou=OrganizationConfig,ou=1.0,ou=sunFMSAML2MetadataService"',
            'requires_name': True,
            'requires_uuid_lookup': False
        }
    }

    def __init__(self):
        """Initialize ChangeService."""
        self.logger = logger
        self.log_service = PAICLogService()
        self.script_service = ScriptAPIService()

    async def _resolve_script_uuid(self, profile_name: str, script_name: str, realm: str = "alpha") -> str:
        """
        Resolve script name to UUID using ScriptAPIService.

        Args:
            profile_name: Connection profile name
            script_name: Script name to resolve
            realm: Target realm (default: "alpha")

        Returns:
            str: Script UUID

        Raises:
            ServiceError: If script not found or multiple scripts found
        """
        self.logger.debug(f"Resolving script name '{script_name}' to UUID")

        # Query scripts by name (exact match)
        scripts = await self.script_service.query_scripts(
            conn_name=profile_name,
            realm=realm,
            query_filter=f'name eq "{script_name}"'
        )

        if not scripts:
            raise ServiceError(f"Script '{script_name}' not found in realm '{realm}'")

        if len(scripts) > 1:
            raise ServiceError(
                f"Multiple scripts found with name '{script_name}' (found {len(scripts)}). "
                f"Script names should be unique."
            )

        script_uuid = scripts[0].get('_id')
        if not script_uuid:
            raise ServiceError(f"Script '{script_name}' has no UUID (_id field missing)")

        self.logger.info(f"Resolved script '{script_name}' to UUID: {script_uuid}")
        return script_uuid

    async def fetch_changes(
        self,
        profile_name: str,
        resource_type: str,
        resource_name: Optional[str] = None,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch configuration changes for a specific resource.

        Args:
            profile_name: Connection profile name
            resource_type: Type of resource
                IDM-Config: endpoint, connector, emailTemplate, mapping, access, repo
                AM-Config: script, journey, saml
            resource_name: Name of the resource (required for some types, optional for others)
                For scripts: Script name (will be resolved to UUID automatically)
                For journeys: Journey name (human-readable)
                For SAML: Entity ID
            start_ts: Start timestamp (ISO-8601 format, optional)
            end_ts: End timestamp (ISO-8601 format, optional)

        Returns:
            Dictionary with:
                - success: bool
                - total_changes: int
                - resource_type: str
                - resource_name: str or None
                - time_range: dict
                - changes: List[dict]  # ConfigChangeEvent.to_dict()

        Raises:
            ValueError: If resource_type is not supported or name validation fails
            ServiceError: If script name lookup fails
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
        requires_name = mapping.get('requires_name', True)

        # Validate name requirement
        if requires_name and not resource_name:
            raise ValueError(
                f"Resource type '{resource_type}' requires a name. "
                f"Use --name to specify the resource name."
            )

        if not requires_name and resource_name:
            self.logger.warning(
                f"Resource type '{resource_type}' does not use name parameter. "
                f"Ignoring provided name '{resource_name}'."
            )

        # Build query filter
        if requires_name:
            # Check if UUID lookup is required (for scripts)
            requires_uuid_lookup = mapping.get('requires_uuid_lookup', False)

            if requires_uuid_lookup:
                # Resolve script name to UUID
                script_uuid = await self._resolve_script_uuid(profile_name, resource_name)
                query_filter = mapping['query_template'].format(uuid=script_uuid)
                log_target = f"'{resource_name}' (UUID: {script_uuid})"
            else:
                # Use name directly
                query_filter = mapping['query_template'].format(name=resource_name)
                log_target = f"'{resource_name}'"
        else:
            query_filter = mapping['query_template']
            log_target = f"(global config)"

        self.logger.info(
            f"Fetching {resource_type} changes for {log_target} "
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

        # Return clean dict for CLI with full metadata
        return {
            "success": True,
            "conn_name": profile_name,
            "source": source,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "total_changes": len(changes),
            "time_range": result.get("time_range", {}),
            "changes": changes
        }
