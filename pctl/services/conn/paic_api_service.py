"""
PAIC API Services for AM resource operations
Provides high-level business logic for different resource types (scripts, journeys, nodes)

Design Philosophy:
- Minimal service - only the 6 core operations from PAIC REST API docs
- No convenience methods (find_by_name, delete_by_name) - build those in specific use cases
- Focus on direct API mapping: query, read, validate, create, update, delete
"""

from loguru import logger

from pctl.core.conn.paic_api import AMAPIClient
from pctl.core.exceptions import ServiceError
from pctl.services.token.token_service import TokenService
from pctl.services.conn.conn_service import ConnectionService


class ScriptAPIService:
    """
    Script-specific API operations - minimal service with only 6 core operations

    API Documentation:
    - Query:    https://docs.pingidentity.com/.../rest-api-scripts-query.html
    - Read:     https://docs.pingidentity.com/.../rest-api-scripts-read.html
    - Validate: https://docs.pingidentity.com/.../rest-api-scripts-validate.html
    - Create:   https://docs.pingidentity.com/.../rest-api-scripts-create.html
    - Update:   https://docs.pingidentity.com/.../rest-api-scripts-update.html
    - Delete:   https://docs.pingidentity.com/.../rest-api-scripts-delete.html
    """

    # Script API version from docs (Accept-API-Version header)
    API_VERSION = "resource=1.1"

    def __init__(self):
        self._token_service = TokenService()
        self._conn_service = ConnectionService()
        self.logger = logger

    async def _get_am_client(self, conn_name: str) -> AMAPIClient:
        """
        Create AM client with token from TokenService

        Args:
            conn_name: Connection profile name

        Returns:
            AMAPIClient: Configured AM API client with script API version

        Raises:
            ServiceError: If token generation or profile retrieval fails
        """
        # Get token from TokenService (service-to-service call)
        token_result = await self._token_service.get_token_from_profile(conn_name)

        if not token_result["success"]:
            raise ServiceError(f"Failed to get token for '{conn_name}': {token_result.get('error')}")

        # Get connection profile from ConnectionService
        profile_result = self._conn_service.get_profile(conn_name)

        if not profile_result["success"]:
            raise ServiceError(f"Failed to get profile '{conn_name}': {profile_result.get('error')}")

        profile = profile_result["profile"]

        # Create AM client with script-specific API version
        return AMAPIClient(
            platform_url=profile['platform_url'],
            access_token=token_result['token'],
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

    # ========== Core API Operations (6 operations from docs) ==========

    async def query_scripts(
        self,
        conn_name: str,
        realm: str = "alpha",
        query_filter: str = "true"
    ) -> list[dict]:
        """
        Query scripts with filter (supports pagination)

        API Doc: https://docs.pingidentity.com/.../rest-api-scripts-query.html

        Args:
            conn_name: Connection profile name
            realm: Target realm (default: "alpha")
            query_filter: SCIM filter expression (default: "true" for all scripts)
                         Examples: 'name eq "MyScript"', 'name co "Test"'

        Returns:
            list[dict]: Complete list of script objects (all pages fetched)

        Example Response Item:
            {
                "_id": "script-uuid",
                "name": "MyScript",
                "script": "base64-encoded-source",
                "language": "JAVASCRIPT",
                "context": "AUTHENTICATION_TREE_DECISION_NODE",
                "description": "...",
                ...
            }
        """
        self.logger.debug(f"Querying scripts from realm '{realm}' with filter: {query_filter}")

        client = await self._get_am_client(conn_name)
        path = self._build_script_path()

        # Fetch all pages (handle pagination)
        all_scripts = []
        page_cookie = None

        while True:
            params = {"_queryFilter": query_filter}
            if page_cookie:
                params["_pagedResultsCookie"] = page_cookie

            result = await client.get(realm, path, params=params)
            scripts = result.get('result', [])
            all_scripts.extend(scripts)

            # Check for next page
            page_cookie = result.get('pagedResultsCookie')
            if not page_cookie:
                break

        self.logger.debug(f"Retrieved {len(all_scripts)} total scripts")
        return all_scripts

    async def read_script(
        self,
        conn_name: str,
        script_id: str,
        realm: str = "alpha"
    ) -> dict:
        """
        Read script by UUID

        API Doc: https://docs.pingidentity.com/.../rest-api-scripts-read.html

        Args:
            conn_name: Connection profile name
            script_id: Script UUID
            realm: Target realm (default: "alpha")

        Returns:
            dict: Complete script object with metadata

        Example Response:
            {
                "_id": "uuid",
                "name": "MyScript",
                "script": "base64-content",
                "language": "JAVASCRIPT",
                "context": "AUTHENTICATION_TREE_DECISION_NODE",
                "createdBy": "user-id",
                "creationDate": "timestamp",
                "lastModifiedBy": "user-id",
                "lastModifiedDate": "timestamp",
                ...
            }
        """
        self.logger.debug(f"Reading script by ID: {script_id}")

        client = await self._get_am_client(conn_name)
        path = self._build_script_path(script_id)

        return await client.get(realm, path)

    async def validate_script(
        self,
        conn_name: str,
        script_content: str,
        language: str = "JAVASCRIPT",
        realm: str = "alpha"
    ) -> dict:
        """
        Validate script syntax

        API Doc: https://docs.pingidentity.com/.../rest-api-scripts-validate.html

        Args:
            conn_name: Connection profile name
            script_content: Base64-encoded script source (UTF-8 encoded, then Base64)
            language: Script language (only "JAVASCRIPT" supported)
            realm: Target realm (default: "alpha")

        Returns:
            dict: Validation result

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

        client = await self._get_am_client(conn_name)
        path = self._build_script_path()

        payload = {
            "script": script_content,
            "language": language
        }

        return await client.post(realm, path, payload=payload, params={"_action": "validate"})

    async def create_script(
        self,
        conn_name: str,
        script_data: dict,
        realm: str = "alpha"
    ) -> dict:
        """
        Create new script

        API Doc: https://docs.pingidentity.com/.../rest-api-scripts-create.html

        Args:
            conn_name: Connection profile name
            script_data: Script data (must include name, script, language, context)
            realm: Target realm (default: "alpha")

        Returns:
            dict: Created script with system-generated metadata (_id, _rev, timestamps)

        Required Fields in script_data:
            - name: Script name
            - script: Base64-encoded script source
            - language: "JAVASCRIPT"
            - context: Script context (e.g., "AUTHENTICATION_TREE_DECISION_NODE")

        Optional Fields:
            - description: Script description
        """
        self.logger.debug(f"Creating script: {script_data.get('name')}")

        client = await self._get_am_client(conn_name)
        path = self._build_script_path()

        return await client.post(realm, path, payload=script_data, params={"_action": "create"})

    async def update_script(
        self,
        conn_name: str,
        script_id: str,
        script_data: dict,
        realm: str = "alpha"
    ) -> dict:
        """
        Update existing script

        API Doc: https://docs.pingidentity.com/.../rest-api-scripts-update.html

        Args:
            conn_name: Connection profile name
            script_id: Script UUID
            script_data: Updated script data (same fields as create)
            realm: Target realm (default: "alpha")

        Returns:
            dict: Updated script object with new metadata

        Note:
            - Cannot update default "ForgeRock Internal" scripts
            - Full replacement (not partial update)
        """
        self.logger.debug(f"Updating script: {script_id}")

        client = await self._get_am_client(conn_name)
        path = self._build_script_path(script_id)

        return await client.put(realm, path, payload=script_data)

    async def delete_script(
        self,
        conn_name: str,
        script_id: str,
        realm: str = "alpha"
    ) -> dict:
        """
        Delete script by UUID

        API Doc: https://docs.pingidentity.com/.../rest-api-scripts-delete.html

        Args:
            conn_name: Connection profile name
            script_id: Script UUID
            realm: Target realm (default: "alpha")

        Returns:
            dict: Empty object {} on success

        Note:
            - Cannot delete default "ForgeRock Internal" scripts
        """
        self.logger.debug(f"Deleting script: {script_id}")

        client = await self._get_am_client(conn_name)
        path = self._build_script_path(script_id)

        return await client.delete(realm, path)


class AMConfigAPIService:
    """
    Generic AM config operations (matches Frodo's AmConfigApi.ts)
    Future implementation for journeys, nodes, services, etc.
    """

    def __init__(self):
        self._token_service = TokenService()
        self._conn_service = ConnectionService()
        self.logger = logger

    async def _get_am_client(self, conn_name: str, api_version: str = "resource=1.1") -> AMAPIClient:
        """Create AM client with token"""
        # Get token from TokenService (service-to-service call)
        token_result = await self._token_service.get_token_from_profile(conn_name)

        if not token_result["success"]:
            raise ServiceError(f"Failed to get token for '{conn_name}': {token_result.get('error')}")

        # Get connection profile from ConnectionService
        profile_result = self._conn_service.get_profile(conn_name)

        if not profile_result["success"]:
            raise ServiceError(f"Failed to get profile '{conn_name}': {profile_result.get('error')}")

        profile = profile_result["profile"]

        return AMAPIClient(
            platform_url=profile['platform_url'],
            access_token=token_result['token'],
            api_version=api_version
        )

    # TODO: Implement when needed for journeys, nodes, etc.
    # Each resource type will have its own path builder and API version
    # Example for journeys: _build_journey_path(), API_VERSION = "protocol=2.1,resource=1.0"
