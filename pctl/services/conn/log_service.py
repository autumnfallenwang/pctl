"""
PAIC Log Service - Internal API for PAIC log streaming operations
Part of the conn domain but separate from profile management
Follows three-layer architecture: Service Layer for business logic and cross-service coordination
"""

import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
from datetime import datetime, timedelta, timezone
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
        query_filter: Optional[str] = None,
        transaction_id: Optional[str] = None,
        level: int = 2,
        use_default_noise_filter: bool = True,
        page_size: int = 1000,
        max_pages_per_window: int = 100,
        max_retries: int = 4
    ) -> Dict[str, Any]:
        """
        Fetch ALL historical logs from PAIC API with automatic pagination and time-window splitting

        This method handles:
        - 24-hour time window splitting (API constraint)
        - Pagination across all pages (pagedResultsCookie)
        - 30-day retention clamping
        - Rate limit handling with exponential backoff
        - Chronological order (old → new) preservation

        Args:
            profile_name: Connection profile to use
            source: Log source(s) to search (e.g., "am-access", "idm-config")
            start_ts: Start timestamp ISO 8601 format (default: 30 days ago)
            end_ts: End timestamp ISO 8601 format (default: now)
            query_filter: Optional PAIC query filter (e.g., '/payload/objectId eq "endpoint/name"')
            transaction_id: Optional transaction ID filter
            level: Log level (1=ERROR, 2=INFO, 3=DEBUG, 4=ALL, default: 2)
            use_default_noise_filter: Apply default noise filtering (default: True)
            page_size: Logs per page (1-1000, default: 1000 for max efficiency)
            max_pages_per_window: Safety limit per 24h window (default: 100 = 100k logs/day max)
            max_retries: Max retry attempts on 429 rate limit errors (default: 4)

        Raises:
            ValueError: If page_size is not between 1 and 1000

        Returns:
            Dict with complete log results:
            {
                "success": True,
                "total_logs": 15430,
                "total_pages": 78,
                "total_windows": 5,
                "time_range": {
                    "start": "2025-10-01T00:00:00.000Z",
                    "end": "2025-10-06T00:00:00.000Z",
                    "requested_days": 5.0,
                    "valid_days": 5.0,
                    "skipped_days": 0.0
                },
                "logs": [...]  # All logs in chronological order (old → new)
            }
        """
        try:
            # Validate page_size constraint (PAIC API limit)
            if not (1 <= page_size <= 1000):
                raise ValueError(f"page_size must be between 1 and 1000, got {page_size}")

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

            # Convert level to string array for filtering
            levels = LogLevelResolver.resolve_level(level)

            # Get noise filter
            noise_filter = NoiseFilter.get_default_noise_filter() if use_default_noise_filter else []

            # Calculate time windows
            time_windows, time_range_info = self._calculate_time_windows(start_ts, end_ts)

            self.logger.info(
                f"Fetching logs from {time_range_info['valid_days']:.1f} days "
                f"({len(time_windows)} windows) from {time_range_info['start']}"
            )

            if time_range_info['skipped_days'] > 0:
                self.logger.warning(
                    f"Skipped {time_range_info['skipped_days']:.1f} days beyond 30-day retention limit"
                )

            # Fetch logs from all windows
            all_logs = []
            total_pages = 0

            for idx, window in enumerate(time_windows, 1):
                self.logger.debug(
                    f"Processing window {idx}/{len(time_windows)}: "
                    f"{window['start']} to {window['end']}"
                )

                window_result = await self._fetch_window_logs(
                    profile=profile,
                    source=source,
                    start_ts=window['start'],
                    end_ts=window['end'],
                    query_filter=query_filter,
                    transaction_id=transaction_id,
                    levels=levels,
                    noise_filter=noise_filter,
                    page_size=page_size,
                    max_pages=max_pages_per_window,
                    max_retries=max_retries
                )

                all_logs.extend(window_result['logs'])
                total_pages += window_result['pages']

                self.logger.debug(
                    f"Window {idx} complete: {window_result['pages']} pages, "
                    f"{len(window_result['logs'])} logs"
                )

            return {
                "success": True,
                "conn_name": profile_name,
                "source": source,
                "query_filter": query_filter,
                "log_level": level,
                "noise_filter_enabled": use_default_noise_filter,
                "total_logs": len(all_logs),
                "total_pages": total_pages,
                "total_windows": len(time_windows),
                "time_range": time_range_info,
                "logs": all_logs
            }

        except Exception as e:
            self.logger.error(f"Failed to fetch historical logs for profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _fetch_with_retry(
        self,
        profile: Any,
        source: str,
        start_ts: str,
        end_ts: str,
        page_size: int,
        cookie: Optional[str],
        query_filter: Optional[str],
        transaction_id: Optional[str],
        max_retries: int
    ) -> Any:
        """
        Make API call with exponential backoff on 429 rate limit errors

        Retry sequence: 4s → 8s → 16s → 32s (total 60s, aligns with rate limit window)

        Args:
            profile: Connection profile
            source: Log source
            start_ts: Start timestamp
            end_ts: End timestamp
            page_size: Logs per page
            cookie: Pagination cookie (None for first page)
            query_filter: Optional query filter
            transaction_id: Optional transaction ID filter
            max_retries: Maximum retry attempts

        Returns:
            LogsResult from PAIC API

        Raises:
            Exception: After max_retries exhausted or non-429 errors
        """
        retry_count = 0

        while retry_count <= max_retries:
            try:
                # Make API call
                result = await self.paic_api.fetch_logs(
                    profile=profile,
                    source=source,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    page_size=page_size,
                    cookie=cookie,
                    query_filter=query_filter,
                    txid=transaction_id
                )

                return result  # Success

            except Exception as e:
                error_str = str(e).lower()

                # Check if it's a 429 rate limit error
                if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
                    if retry_count >= max_retries:
                        self.logger.error(f"Rate limit retry exhausted after {max_retries} attempts")
                        raise

                    retry_count += 1
                    wait_time = 2 ** (retry_count + 1)  # 4s, 8s, 16s, 32s

                    self.logger.warning(
                        f"Rate limited (429), retry {retry_count}/{max_retries}, "
                        f"waiting {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Non-429 error, don't retry
                    raise

    async def _fetch_window_logs(
        self,
        profile: Any,
        source: str,
        start_ts: str,
        end_ts: str,
        query_filter: Optional[str],
        transaction_id: Optional[str],
        levels: List[str],
        noise_filter: List[str],
        page_size: int,
        max_pages: int,
        max_retries: int
    ) -> Dict[str, Any]:
        """
        Fetch all pages for one 24-hour time window with pagination and filtering

        Filtering is applied in innermost loop to save memory (don't store filtered-out logs)

        Args:
            profile: Connection profile
            source: Log source
            start_ts: Window start timestamp
            end_ts: Window end timestamp
            query_filter: Optional query filter
            transaction_id: Optional transaction ID filter
            levels: Log levels to include (resolved from numeric level)
            noise_filter: Noise filter patterns to exclude
            page_size: Logs per page
            max_pages: Safety limit (prevents infinite loops)
            max_retries: Max retries on 429 errors

        Returns:
            Dict with filtered logs and page count:
            {"logs": [...], "pages": 5}
        """
        logs = []
        cookie = None
        pages = 0

        while True:
            # Make API call with retry logic
            result = await self._fetch_with_retry(
                profile=profile,
                source=source,
                start_ts=start_ts,
                end_ts=end_ts,
                page_size=page_size,
                cookie=cookie,
                query_filter=query_filter,
                transaction_id=transaction_id,
                max_retries=max_retries
            )

            # Filter logs in innermost loop (save memory by not keeping filtered-out logs)
            # Convert to dict immediately for clean service layer contract
            if result.result:
                for log_event in result.result:
                    if self.paic_streamer._should_include_log(log_event, levels, transaction_id, noise_filter):
                        # Convert LogEvent to dict immediately (no extra iteration needed)
                        logs.append({
                            "timestamp": log_event.timestamp,
                            "type": log_event.type,
                            "source": log_event.source,
                            "payload": log_event.payload
                        })

            pages += 1

            # Check for next page
            cookie = result.pagedResultsCookie
            if not cookie:
                break  # No more pages

            # Safety check
            if pages >= max_pages:
                self.logger.warning(
                    f"Hit max pages limit ({max_pages}) for window {start_ts} to {end_ts}"
                )
                break

            # No artificial delay - response time provides natural throttling

        return {"logs": logs, "pages": pages}

    def _calculate_time_windows(
        self,
        start_ts: Optional[str],
        end_ts: Optional[str]
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Calculate 24-hour time windows and clamp to 30-day retention

        Default behavior:
        - No start_ts → defaults to 24 hours ago
        - No end_ts → defaults to now
        - Both None → queries last 24 hours
        - Only start_ts → from start_ts to now
        - Only end_ts → from 24 hours before end_ts to end_ts

        Args:
            start_ts: Start timestamp (ISO 8601) or None for 24 hours ago
            end_ts: End timestamp (ISO 8601) or None for now

        Returns:
            Tuple of (windows_list, time_range_info):
            - windows_list: [{"start": "...", "end": "..."}, ...]  (chronological order)
            - time_range_info: {"start": "...", "end": "...", "requested_days": 5.0, ...}
        """
        now = datetime.now(timezone.utc)
        retention_limit = now - timedelta(days=30)

        # Parse or default time range
        if end_ts:
            end_time = datetime.fromisoformat(end_ts.replace('Z', '+00:00'))
        else:
            end_time = now

        if start_ts:
            start_time = datetime.fromisoformat(start_ts.replace('Z', '+00:00'))
            original_start = start_time
        else:
            # Default: 24 hours before end_time
            start_time = end_time - timedelta(hours=24)
            original_start = start_time

        # Clamp to 30-day retention
        skipped_days = 0.0
        if start_time < retention_limit:
            skipped_days = (retention_limit - start_time).total_seconds() / 86400
            start_time = retention_limit

        # Ensure chronological order
        if start_time >= end_time:
            raise ValueError(f"Start time ({start_time}) must be before end time ({end_time})")

        # Split into 24-hour windows (oldest → newest)
        windows = []
        current = start_time

        while current < end_time:
            window_end = min(current + timedelta(hours=24), end_time)
            windows.append({
                "start": current.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "end": window_end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            })
            current = window_end

        # Calculate time range info
        requested_days = (end_time - original_start).total_seconds() / 86400
        valid_days = (end_time - start_time).total_seconds() / 86400

        time_range_info = {
            "start": start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "end": end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "requested_days": int(round(requested_days)) if abs(requested_days - round(requested_days)) < 0.001 else round(requested_days, 2),
            "valid_days": int(round(valid_days)) if abs(valid_days - round(valid_days)) < 0.001 else round(valid_days, 2),
            "skipped_days": 0 if skipped_days == 0 else (int(round(skipped_days)) if abs(skipped_days - round(skipped_days)) < 0.001 else round(skipped_days, 2))
        }

        return windows, time_range_info

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