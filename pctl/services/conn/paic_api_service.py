"""
PAIC API Services for AM resource operations
Provides high-level business logic for different resource types (scripts, journeys, nodes)
"""

from typing import Optional
from loguru import logger

from pctl.core.conn.paic_api import AMAPIClient
from pctl.services.token.token_service import TokenService
from pctl.services.conn.conn_service import ConnectionService
from pctl.core.exceptions import ServiceError


class ScriptAPIService:
    """
    Script-specific API operations (matches Frodo's ScriptApi.ts)
    Provides high-level script operations with name resolution
    """

    # Script API uses specific version (matches Frodo)
    API_VERSION = "protocol=2.0,resource=1.0"

    def __init__(self):
        self._token_service = TokenService()
        self._conn_service = ConnectionService()
        self.logger = logger

    def _get_am_client(self, conn_name: str) -> AMAPIClient:
        """
        Create AM client with token from TokenService

        Args:
            conn_name: Connection profile name

        Returns:
            AMAPIClient: Configured AM API client with script API version
        """
        # Get token from TokenService (service-to-service call)
        token_data = self._token_service.get_token(conn_name)

        # Get connection profile from ConnectionService
        conn = self._conn_service.get_profile(conn_name)

        # Create AM client with script-specific API version
        return AMAPIClient(
            platform_url=conn['platform_url'],
            access_token=token_data['access_token'],
            api_version=self.API_VERSION
        )

    def _build_script_path(self, script_id: str | None = None) -> str:
        """
        Build script resource path (after realm)

        Args:
            script_id: Optional script UUID for specific script

        Returns:
            str: Resource path like "scripts" or "scripts/{uuid}"
        """
        return f"scripts/{script_id}" if script_id else "scripts"

    # ========== Query Operations ==========

    def get_all_scripts(self, conn_name: str, realm: str = "alpha") -> list[dict]:
        """
        Get all scripts in realm (matches Frodo's getScripts)

        Args:
            conn_name: Connection profile name
            realm: Target realm (default: "alpha")

        Returns:
            list[dict]: List of script objects
        """
        self.logger.debug(f"Getting all scripts from realm: {realm}")

        client = self._get_am_client(conn_name)
        path = self._build_script_path()

        result = client.get(realm, path, params={"_queryFilter": "true"})
        return result.get('result', [])

    def find_script_by_name(
        self,
        conn_name: str,
        script_name: str,
        realm: str = "alpha"
    ) -> Optional[dict]:
        """
        Find script by name, return script object or None (matches Frodo's getScriptByName)

        Args:
            conn_name: Connection profile name
            script_name: Script name to search for
            realm: Target realm (default: "alpha")

        Returns:
            Optional[dict]: Script object if found, None otherwise

        Example Return:
            {
                "_id": "script-uuid",
                "name": "MyScript",
                "script": "base64-encoded-source",
                "language": "JAVASCRIPT",
                "context": "AUTHENTICATION_TREE_DECISION_NODE",
                ...
            }
        """
        self.logger.debug(f"Finding script by name: {script_name} in realm: {realm}")

        client = self._get_am_client(conn_name)
        path = self._build_script_path()
        query = f'name eq "{script_name}"'

        result = client.get(realm, path, params={"_queryFilter": query})
        scripts = result.get('result', [])

        if not scripts:
            self.logger.debug(f"Script not found: {script_name}")
            return None

        if len(scripts) > 1:
            self.logger.warning(f"Multiple scripts found with name '{script_name}', returning first match")

        return scripts[0]

    def get_script_by_id(
        self,
        conn_name: str,
        script_id: str,
        realm: str = "alpha"
    ) -> dict:
        """
        Get script by UUID (matches Frodo's getScript)

        Args:
            conn_name: Connection profile name
            script_id: Script UUID
            realm: Target realm (default: "alpha")

        Returns:
            dict: Complete script object

        Raises:
            ServiceError: If script not found or API error
        """
        self.logger.debug(f"Getting script by ID: {script_id}")

        client = self._get_am_client(conn_name)
        path = self._build_script_path(script_id)

        return client.get(realm, path)

    # ========== Create/Update/Delete Operations ==========

    def create_script(
        self,
        conn_name: str,
        script_data: dict,
        realm: str = "alpha"
    ) -> dict:
        """
        Create new script (POST with _action=create)

        Args:
            conn_name: Connection profile name
            script_data: Script data (must include name, script, language, context)
            realm: Target realm

        Returns:
            dict: Created script with system-generated metadata
        """
        self.logger.debug(f"Creating script: {script_data.get('name')}")

        client = self._get_am_client(conn_name)
        path = self._build_script_path()

        return client.post(realm, path, payload=script_data, params={"_action": "create"})

    def update_script(
        self,
        conn_name: str,
        script_id: str,
        script_data: dict,
        realm: str = "alpha"
    ) -> dict:
        """
        Update existing script (matches Frodo's putScript)

        Args:
            conn_name: Connection profile name
            script_id: Script UUID
            script_data: Updated script data
            realm: Target realm

        Returns:
            dict: Updated script object
        """
        self.logger.debug(f"Updating script: {script_id}")

        client = self._get_am_client(conn_name)
        path = self._build_script_path(script_id)

        return client.put(realm, path, payload=script_data)

    def delete_script(
        self,
        conn_name: str,
        script_id: str,
        realm: str = "alpha"
    ) -> dict:
        """
        Delete script by UUID (matches Frodo's deleteScript)

        Args:
            conn_name: Connection profile name
            script_id: Script UUID
            realm: Target realm

        Returns:
            dict: Empty object {} on success
        """
        self.logger.debug(f"Deleting script: {script_id}")

        client = self._get_am_client(conn_name)
        path = self._build_script_path(script_id)

        return client.delete(realm, path)

    def delete_script_by_name(
        self,
        conn_name: str,
        script_name: str,
        realm: str = "alpha"
    ) -> dict:
        """
        Delete script by name (matches Frodo's deleteScriptByName)
        Finds script by name first, then deletes by UUID

        Args:
            conn_name: Connection profile name
            script_name: Script name
            realm: Target realm

        Returns:
            dict: Empty object {} on success

        Raises:
            ServiceError: If script not found
        """
        self.logger.debug(f"Deleting script by name: {script_name}")

        # Find script by name first
        script = self.find_script_by_name(conn_name, script_name, realm)

        if not script:
            raise ServiceError(f"Script with name '{script_name}' does not exist")

        # Delete by UUID
        return self.delete_script(conn_name, script['_id'], realm)

    # ========== Validation Operations ==========

    def validate_script(
        self,
        conn_name: str,
        script_content: str,
        language: str = "JAVASCRIPT",
        realm: str = "alpha"
    ) -> dict:
        """
        Validate script syntax

        Args:
            conn_name: Connection profile name
            script_content: Base64-encoded script source
            language: Script language (default: "JAVASCRIPT")
            realm: Target realm

        Returns:
            dict: Validation result {"success": bool, "errors": [...]}

        Example Response (valid):
            {"success": true}

        Example Response (invalid):
            {
                "success": false,
                "errors": [
                    {"line": 10, "column": 5, "message": "Unexpected token '}'"}
                ]
            }
        """
        self.logger.debug(f"Validating script (language: {language})")

        client = self._get_am_client(conn_name)
        path = self._build_script_path()

        payload = {
            "script": script_content,
            "language": language
        }

        return client.post(realm, path, payload=payload, params={"_action": "validate"})


class AMConfigAPIService:
    """
    Generic AM config operations (matches Frodo's AmConfigApi.ts)
    Future implementation for journeys, nodes, services, etc.
    """

    def __init__(self):
        self._token_service = TokenService()
        self._conn_service = ConnectionService()
        self.logger = logger

    def _get_am_client(self, conn_name: str, api_version: str = "resource=1.1") -> AMAPIClient:
        """Create AM client with token"""
        token_data = self._token_service.get_token(conn_name)
        conn = self._conn_service.get_profile(conn_name)

        return AMAPIClient(
            platform_url=conn['platform_url'],
            access_token=token_data['access_token'],
            api_version=api_version
        )

    # TODO: Implement when needed for journeys, nodes, etc.
    # Each resource type will have its own path builder and API version
    # Example for journeys: _build_journey_path(), API_VERSION = "protocol=2.1,resource=1.0"
