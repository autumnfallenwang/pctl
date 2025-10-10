"""
PAIC REST API operations for log streaming and AM API access
Exactly mimics Frodo's behavior from frodo-lib/src/api/cloud/LogApi.ts and frodo-cli/src/ops/LogOps.ts

AMAPIClient exactly matches Frodo's generateAmApi() factory pattern from BaseApi.ts
"""

import json
import asyncio
from typing import Optional, List, Dict, Any, AsyncIterator
from urllib.parse import quote
from loguru import logger

from .conn_models import ConnectionProfile
from .log_models import LogEvent, PagedLogResult, LogLevelResolver, NoiseFilter
from ..http_client import HTTPClient
from ..exceptions import ServiceError


class PAICLogAPI:
    """
    PAIC Log API operations - exactly mimics Frodo's LogApi.ts behavior
    Only accessible by services/conn/ (domain boundary rule)
    """

    def __init__(self, http_client: Optional[HTTPClient] = None):
        self.logger = logger
        self.http_client = http_client or HTTPClient()

    async def tail_logs(
        self,
        profile: ConnectionProfile,
        source: str,
        cookie: Optional[str] = None
    ) -> PagedLogResult:
        """
        Tail logs from PAIC API (exactly matches Frodo's tail function)
        URL template: {host}/monitoring/logs/tail?source={source}
        """
        if not profile.has_log_credentials():
            raise ServiceError(f"Log API credentials not configured for profile '{profile.name}'")

        # Build URL exactly like Frodo does
        base_url = profile.platform_url.rstrip('/')
        url = f"{base_url}/monitoring/logs/tail?source={quote(source)}"

        if cookie:
            url += f"&_pagedResultsCookie={quote(cookie)}"

        self.logger.debug(f"Tailing logs from: {url}")

        try:
            # Use log auth headers from profile
            headers = profile.get_log_auth_headers()

            # Make the API call using our HTTPClient
            async with self.http_client._create_client() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                response_data = response.json()

            # Convert response to our models (matching Frodo's structure)
            log_events = []
            if 'result' in response_data and isinstance(response_data['result'], list):
                for event_data in response_data['result']:
                    log_event = self._parse_log_event(event_data)
                    if log_event:
                        log_events.append(log_event)

            return PagedLogResult(
                result=log_events,
                pagedResultsCookie=response_data.get('pagedResultsCookie'),
                totalPagedResultsPolicy=response_data.get('totalPagedResultsPolicy'),
                totalPagedResults=response_data.get('totalPagedResults'),
                remainingPagedResults=response_data.get('remainingPagedResults')
            )

        except Exception as e:
            self.logger.error(f"Failed to tail logs from {url}: {e}")
            raise ServiceError(f"Log tail API error: {e}")

    async def fetch_logs(
        self,
        profile: ConnectionProfile,
        source: str,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        cookie: Optional[str] = None,
        txid: Optional[str] = None,
        query_filter: Optional[str] = None,
        page_size: Optional[int] = None
    ) -> PagedLogResult:
        """
        Fetch historical logs from PAIC API (exactly matches Frodo's fetch function)
        URL template: {host}/monitoring/logs?source={source}
        """
        if not profile.has_log_credentials():
            raise ServiceError(f"Log API credentials not configured for profile '{profile.name}'")

        # Build URL exactly like Frodo does
        base_url = profile.platform_url.rstrip('/')
        url = f"{base_url}/monitoring/logs?source={quote(source)}"

        # Add query parameters exactly like Frodo
        if start_ts and end_ts:
            url += f"&beginTime={start_ts}&endTime={end_ts}"

        if txid:
            url += f"&transactionId={txid}"

        if query_filter:
            url += f"&_queryFilter={quote(query_filter)}"

        if cookie:
            url += f"&_pagedResultsCookie={quote(cookie)}"

        if page_size:
            url += f"&_pageSize={page_size}"

        self.logger.debug(f"Fetching logs from: {url}")

        try:
            # Use log auth headers from profile
            headers = profile.get_log_auth_headers()

            # Make the API call with longer timeout for historical queries
            async with self.http_client._create_client() as client:
                response = await client.get(url, headers=headers, timeout=60.0)
                response.raise_for_status()
                response_data = response.json()

            # Convert response to our models (matching Frodo's structure)
            log_events = []
            if 'result' in response_data and isinstance(response_data['result'], list):
                for event_data in response_data['result']:
                    log_event = self._parse_log_event(event_data)
                    if log_event:
                        log_events.append(log_event)

            return PagedLogResult(
                result=log_events,
                pagedResultsCookie=response_data.get('pagedResultsCookie'),
                totalPagedResultsPolicy=response_data.get('totalPagedResultsPolicy'),
                totalPagedResults=response_data.get('totalPagedResults'),
                remainingPagedResults=response_data.get('remainingPagedResults')
            )

        except Exception as e:
            self.logger.error(f"Failed to fetch logs from {url}: {e}")
            raise ServiceError(f"Log fetch API error: {e}")

    async def get_log_sources(self, profile: ConnectionProfile) -> List[str]:
        """
        Get available log sources from PAIC API (exactly matches Frodo's getSources function)
        URL template: {host}/monitoring/logs/sources
        """
        if not profile.has_log_credentials():
            raise ServiceError(f"Log API credentials not configured for profile '{profile.name}'")

        # Build URL exactly like Frodo does
        base_url = profile.platform_url.rstrip('/')
        url = f"{base_url}/monitoring/logs/sources"

        self.logger.debug(f"Getting log sources from: {url}")

        try:
            # Use log auth headers from profile
            headers = profile.get_log_auth_headers()

            # Make the API call
            async with self.http_client._create_client() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                response_data = response.json()

            # Extract sources list (matches Frodo's behavior)
            if 'result' in response_data and isinstance(response_data['result'], list):
                return response_data['result']
            else:
                return []

        except Exception as e:
            self.logger.error(f"Failed to get log sources from {url}: {e}")
            raise ServiceError(f"Log sources API error: {e}")

    def _parse_log_event(self, event_data: Dict[str, Any]) -> Optional[LogEvent]:
        """
        Parse raw log event data into LogEvent model
        Handles both string and dict payloads with no assumptions about structure
        """
        try:
            # Basic event structure
            log_event = LogEvent(
                timestamp=event_data.get('timestamp', ''),
                type=event_data.get('type', ''),
                source=event_data.get('source', ''),
                payload=''  # Will be set below
            )

            # Handle payload based on type (matching Frodo's flexible approach)
            raw_payload = event_data.get('payload')

            if log_event.type == 'text/plain':
                # For text/plain, payload is a string
                log_event.payload = str(raw_payload) if raw_payload else ''
            else:
                # For structured logs, keep as dict (no assumptions about structure)
                if isinstance(raw_payload, dict):
                    log_event.payload = raw_payload
                else:
                    # Fallback to string representation
                    log_event.payload = str(raw_payload) if raw_payload else ''

            return log_event

        except Exception as e:
            self.logger.debug(f"Failed to parse log event: {e}")
            return None


class PAICLogStreamer:
    """
    Log streaming service that exactly mimics Frodo's tailLogs behavior
    Handles continuous polling, filtering, and output
    """

    def __init__(self, paic_api: Optional[PAICLogAPI] = None):
        self.logger = logger
        self.paic_api = paic_api or PAICLogAPI()

    async def stream_logs(
        self,
        profile: ConnectionProfile,
        source: str,
        levels: List[str],
        txid: Optional[str] = None,
        noise_filter: Optional[List[str]] = None,
        cookie: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Stream logs continuously (exactly matches Frodo's tailLogs behavior)
        Yields JSON strings of filtered log events
        """
        # Use default noise filter if none provided (matching Frodo)
        if noise_filter is None:
            noise_filter = NoiseFilter.get_default_noise_filter()

        try:
            while True:
                # 1. Make API call (matching Frodo's tail function)
                logs_result = await self.paic_api.tail_logs(profile, source, cookie)

                # 2. Apply filtering (exactly matching Frodo's filter logic)
                filtered_logs = []
                if logs_result.result:
                    for log_event in logs_result.result:
                        if self._should_include_log(log_event, levels, txid, noise_filter):
                            filtered_logs.append(log_event)

                # 3. Yield each filtered log as JSON (matching Frodo's output)
                for log_event in filtered_logs:
                    yield self._log_event_to_json(log_event)

                # 4. Update cookie for next iteration
                cookie = logs_result.pagedResultsCookie

                # 5. Wait exactly 5 seconds (matching Frodo's timeout)
                await asyncio.sleep(5.0)

        except Exception as e:
            self.logger.error(f"Log streaming error: {e}")
            # Don't crash - just log error and continue (matching Frodo behavior)
            yield f'{{"error": "Log streaming error: {str(e)}"}}'

    def _should_include_log(
        self,
        log_event: LogEvent,
        levels: List[str],
        txid: Optional[str],
        noise_filter: List[str]
    ) -> bool:
        """
        Apply filtering logic exactly matching Frodo's filter chain
        Order: noise filter → level filter → transaction ID filter
        """
        # 1. Noise filter check (matching Frodo's logic)
        if isinstance(log_event.payload, dict):
            if log_event.payload.get('logger') in noise_filter:
                return False
        if log_event.type in noise_filter:
            return False

        # 2. Level filter check (matching Frodo's logic with 'ALL' special case)
        if levels and levels[0] != 'ALL':
            event_level = LogLevelResolver.resolve_payload_level(log_event)
            if event_level and event_level not in levels:
                return False

        # 3. Transaction ID filter check (matching Frodo's logic)
        if txid:
            if isinstance(log_event.payload, dict):
                payload_txid = log_event.payload.get('transactionId')
                if not payload_txid or txid not in payload_txid:
                    return False

        return True

    def _log_event_to_json(self, log_event: LogEvent) -> str:
        """
        Convert LogEvent to JSON string exactly matching Frodo's output format
        """
        try:
            # Convert to dict for JSON serialization
            event_dict = {
                'timestamp': log_event.timestamp,
                'type': log_event.type,
                'source': log_event.source,
                'payload': log_event.payload
            }

            # Payload is already str or dict - no conversion needed
            # Just pass it through as-is

            # Return JSON string (matching Frodo's JSON.stringify)
            return json.dumps(event_dict, separators=(',', ':'))

        except Exception as e:
            self.logger.debug(f"Failed to serialize log event: {e}")
            return f'{{"error": "Failed to serialize log event: {str(e)}"}}'


class AMAPIClient:
    """
    Low-level AM REST API client - Pre-configured HTTP client for AM APIs

    Provides generic HTTP methods (get, post, put, delete) with AM-specific headers.
    Does NOT provide resource-specific methods (scripts, trees, etc.) - those belong
    in service layer (ScriptAPIService, etc.)

    Exactly matches Frodo's generateAmApi() factory pattern.
    Only accessible by services/conn/ (domain boundary rule)
    """

    def __init__(self, platform_url: str, access_token: str, api_version: str = "resource=1.1"):
        """
        Args:
            platform_url: Base platform URL from connection profile
            access_token: Bearer token (provided by caller, not generated here)
            api_version: Default API version header (can be overridden per request)
        """
        self.platform_url = platform_url.rstrip('/')
        self.access_token = access_token
        self.default_api_version = api_version
        self.http_client = HTTPClient()
        self.logger = logger

    def _get_headers(self, api_version: str | None = None) -> dict:
        """
        Get AM-specific headers (matches Frodo's generateAmApi headers)

        Args:
            api_version: Override default API version

        Returns:
            dict: Headers with Authorization, Accept-API-Version, Content-Type
        """
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept-API-Version": api_version or self.default_api_version,
            "Content-Type": "application/json"
        }

    # ========== Generic HTTP Methods (like Frodo's Axios instance) ==========

    async def get(
        self,
        realm: str,
        path: str,
        params: dict | None = None,
        api_version: str | None = None
    ) -> dict:
        """
        Generic GET request (matches Frodo's axios.get())

        Args:
            realm: Target realm (e.g., "alpha")
            path: Resource path after realm (e.g., "scripts", "scripts/{uuid}")
            params: Query parameters (e.g., {"_queryFilter": "true"})
            api_version: Override default API version

        Returns:
            dict: JSON response

        Example:
            client.get("alpha", "scripts", {"_queryFilter": "true"})
        """
        url = f"{self.platform_url}/am/json/realms/root/realms/{realm}/{path}"

        try:
            response = await self.http_client.get_response(
                url,
                params=params,
                headers=self._get_headers(api_version)
            )
            return response.json()

        except Exception as e:
            self.logger.error(f"AM GET failed: {url}, error: {e}")
            raise ServiceError(f"AM GET API error: {e}")

    async def post(
        self,
        realm: str,
        path: str,
        payload: dict | None = None,
        params: dict | None = None,
        api_version: str | None = None
    ) -> dict:
        """
        Generic POST request (matches Frodo's axios.post())

        Args:
            realm: Target realm (e.g., "alpha")
            path: Resource path after realm (e.g., "scripts")
            payload: Request body (JSON)
            params: Query parameters (e.g., {"_action": "create"})
            api_version: Override default API version

        Returns:
            dict: JSON response

        Example:
            client.post(
                "alpha",
                "scripts",
                payload={"name": "MyScript", ...},
                params={"_action": "create"}
            )
        """
        url = f"{self.platform_url}/am/json/realms/root/realms/{realm}/{path}"

        try:
            response = await self.http_client.post_response(
                url,
                json=payload or {},
                params=params,
                headers=self._get_headers(api_version)
            )
            return response.json()

        except Exception as e:
            self.logger.error(f"AM POST failed: {url}, error: {e}")
            raise ServiceError(f"AM POST API error: {e}")

    async def put(
        self,
        realm: str,
        path: str,
        payload: dict,
        api_version: str | None = None
    ) -> dict:
        """
        Generic PUT request (matches Frodo's axios.put())

        Args:
            realm: Target realm (e.g., "alpha")
            path: Resource path after realm (e.g., "scripts/{uuid}")
            payload: Request body (JSON)
            api_version: Override default API version

        Returns:
            dict: JSON response

        Example:
            client.put(
                "alpha",
                "scripts/uuid-123",
                payload={"name": "UpdatedScript", ...}
            )
        """
        url = f"{self.platform_url}/am/json/realms/root/realms/{realm}/{path}"

        try:
            response = await self.http_client.put_response(
                url,
                json=payload,
                headers=self._get_headers(api_version)
            )
            return response.json()

        except Exception as e:
            self.logger.error(f"AM PUT failed: {url}, error: {e}")
            raise ServiceError(f"AM PUT API error: {e}")

    async def delete(
        self,
        realm: str,
        path: str,
        api_version: str | None = None
    ) -> dict:
        """
        Generic DELETE request (matches Frodo's axios.delete())

        Args:
            realm: Target realm (e.g., "alpha")
            path: Resource path after realm (e.g., "scripts/{uuid}")
            api_version: Override default API version

        Returns:
            dict: JSON response (usually empty {})

        Example:
            client.delete("alpha", "scripts/uuid-123")
        """
        url = f"{self.platform_url}/am/json/realms/root/realms/{realm}/{path}"

        try:
            response = await self.http_client.delete_response(
                url,
                headers=self._get_headers(api_version)
            )
            return response.json()

        except Exception as e:
            self.logger.error(f"AM DELETE failed: {url}, error: {e}")
            raise ServiceError(f"AM DELETE API error: {e}")