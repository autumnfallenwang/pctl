"""
Core models for configuration change tracking.

This module defines data structures for parsing and representing
PAIC configuration change events from audit logs.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


# class ChangeContent(BaseModel):
#     """
#     DEPRECATED: Replaced by raw dict storage in ConfigChangeEvent.content
#
#     Content of a configuration change (source code, globals, etc.).
#
#     Attributes:
#         type: Content type - "text/javascript" or "application/json"
#         source: Source code (JS) or config (JSON) - preserved as-is
#         globals: Global configuration object (optional, from globalsObject field)
#         description: Resource description (optional)
#         resource_id: Resource identifier from after._id field (e.g., "endpoint/example_endpoint")
#     """
#     type: str = Field(..., description="Content type (text/javascript or application/json)")
#     source: str = Field(..., description="Source code or configuration content")
#     globals: Optional[str] = Field(None, description="Global configuration object from globalsObject")
#     description: Optional[str] = Field(default="", description="Resource description")
#     resource_id: Optional[str] = Field(None, description="Resource ID from after._id")


class ConfigChangeEvent(BaseModel):
    """
    Universal configuration change event for both AM-Config and IDM-Config.

    Represents one CREATE/UPDATE/DELETE operation on a config resource.
    Works for all PAIC object types without custom content models.

    Attributes:
        event_id: Unique change event ID from payload._id (e.g., "abc123-def456-789")
        timestamp: When the change occurred (ISO-8601 format)
        operation: Type of operation - CREATE, UPDATE, DELETE, PATCH
        user_id: ID of user who made the change (from userId field)
        transaction_id: Audit transaction ID for traceability
        object_id: Full object identifier from payload.objectId (LDAP DN for AM, type/name for IDM)
        realm: PAIC realm (e.g., "/alpha")
        resource_type: Resource type from CLI input (endpoint, journey, script, etc.)
        content: Raw 'after' content as dict (IDM-Config only, None for AM-Config)
    """
    event_id: str = Field(..., description="Unique change event ID from payload._id")
    timestamp: str = Field(..., description="Change timestamp in ISO-8601 format")
    operation: str = Field(..., description="Operation type: CREATE, UPDATE, DELETE, PATCH")
    user_id: str = Field(..., description="User ID who made the change")
    transaction_id: str = Field(..., description="Audit transaction ID")
    object_id: str = Field(..., description="Full object identifier from payload.objectId")
    realm: Optional[str] = Field(None, description="PAIC realm (e.g., '/alpha', None for IDM)")
    resource_type: str = Field(..., description="Resource type (endpoint, journey, script)")
    content: Optional[Dict[str, Any]] = Field(None, description="Raw 'after' content (IDM only, None for AM)")

    @classmethod
    def from_log_entry(cls, log_entry: Dict[str, Any], resource_type: str) -> "ConfigChangeEvent":
        """
        Parse a raw log entry into a ConfigChangeEvent.

        Args:
            log_entry: Raw log entry from PAICLogService.fetch_historical_logs()
            resource_type: Type of resource being tracked (endpoint, journey, script)

        Returns:
            ConfigChangeEvent instance

        Example IDM-Config log_entry structure:
            {
                "timestamp": "2025-10-03T03:59:02.242Z",
                "type": "application/json",
                "source": "idm-config",
                "payload": {
                    "_id": "abc123-def456-789",
                    "operation": "CREATE",
                    "userId": "user-uuid-123",
                    "transactionId": "txn-123-456",
                    "objectId": "endpoint/example_endpoint",
                    "timestamp": "2025-10-03T03:59:02.240Z",
                    "after": {
                        "_id": "endpoint/example_endpoint",
                        "description": "Example endpoint description",
                        "globalsObject": "{\n  \"request\": {...}\n}",
                        "source": "var result = ...",
                        "type": "text/javascript"
                    }
                }
            }

        Example AM-Config log_entry structure:
            {
                "timestamp": "2025-10-01T08:58:09.570Z",
                "source": "audit",
                "payload": {
                    "_id": "event-uuid-123",
                    "objectId": "ou=ExampleJourney,ou=default,ou=OrganizationConfig,...",
                    "operation": "UPDATE",
                    "userId": "id=user123,ou=user,ou=am-config",
                    "transactionId": "txn-uuid-456",
                    "realm": "/realm",
                    "changedFields": ["nodes", "staticNodes"]
                }
            }
        """
        # Both AM and IDM have payload structure
        payload = log_entry.get("payload", log_entry)

        # Extract common fields (all from payload)
        event_id = payload.get("_id", "")
        timestamp = payload.get("timestamp", "")
        operation = payload.get("operation", "UNKNOWN")
        user_id = payload.get("userId", "")
        transaction_id = payload.get("transactionId", "")
        object_id = payload.get("objectId", "")
        realm = payload.get("realm")  # None for IDM, string for AM

        # Extract content from 'after' field (None for AM-Config, dict for IDM-Config)
        content = payload.get("after")

        return cls(
            event_id=event_id,
            timestamp=timestamp,
            operation=operation,
            user_id=user_id,
            transaction_id=transaction_id,
            object_id=object_id,
            realm=realm,
            resource_type=resource_type,
            content=content
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for service layer communication.

        Returns clean dict without nested models for CLI consumption.
        """
        result = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "operation": self.operation,
            "user_id": self.user_id,
            "transaction_id": self.transaction_id,
            "object_id": self.object_id,
            "realm": self.realm,
            "resource_type": self.resource_type,
            "content": self.content  # Raw dict or None
        }

        return result
