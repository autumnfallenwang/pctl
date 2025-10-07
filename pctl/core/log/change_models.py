"""
Core models for configuration change tracking.

This module defines data structures for parsing and representing
PAIC configuration change events from audit logs.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChangeContent(BaseModel):
    """
    Content of a configuration change (source code, globals, etc.).

    Attributes:
        type: Content type - "text/javascript" or "application/json"
        source: Source code (JS) or config (JSON) - preserved as-is
        globals: Global configuration object (optional, from globalsObject field)
        description: Resource description (optional)
        resource_id: Resource identifier from after._id field (e.g., "endpoint/example_endpoint")
    """
    type: str = Field(..., description="Content type (text/javascript or application/json)")
    source: str = Field(..., description="Source code or configuration content")
    globals: Optional[str] = Field(None, description="Global configuration object from globalsObject")
    description: Optional[str] = Field(default="", description="Resource description")
    resource_id: Optional[str] = Field(None, description="Resource ID from after._id")


class ConfigChangeEvent(BaseModel):
    """
    A single configuration change event from PAIC audit logs.

    Represents one CREATE/UPDATE/DELETE operation on a config resource
    (endpoint, journey, script, etc.)

    Attributes:
        event_id: Unique change event ID from payload._id (e.g., "abc123-def456-789")
        timestamp: When the change occurred (ISO-8601 format)
        operation: Type of operation - CREATE, UPDATE, or DELETE
        user_id: ID of user who made the change (from userId field)
        transaction_id: Audit transaction ID for traceability
        resource_type: Type of resource (endpoint, journey, script, etc.)
        content: Current state after the change (source, globals, resource_id, etc.)
    """
    event_id: str = Field(..., description="Unique change event ID from payload._id")
    timestamp: str = Field(..., description="Change timestamp in ISO-8601 format")
    operation: str = Field(..., description="Operation type: CREATE, UPDATE, DELETE")
    user_id: str = Field(..., description="User ID who made the change")
    transaction_id: str = Field(..., description="Audit transaction ID")
    resource_type: str = Field(..., description="Resource type (endpoint, journey, script)")
    content: ChangeContent = Field(..., description="Content after the change")

    @classmethod
    def from_log_entry(cls, log_entry: Dict[str, Any], resource_type: str) -> "ConfigChangeEvent":
        """
        Parse a raw log entry into a ConfigChangeEvent.

        Args:
            log_entry: Raw log entry from PAICLogService.fetch_historical_logs()
            resource_type: Type of resource being tracked (endpoint, journey, script)

        Returns:
            ConfigChangeEvent instance

        Example log_entry structure:
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
                    },
                    "before": null  # Can be null for CREATE operations
                }
            }
        """
        payload = log_entry["payload"]
        after = payload.get("after", {})

        # Extract content fields from 'after' object
        content = ChangeContent(
            type=after.get("type", "text/javascript"),
            source=after.get("source", ""),
            globals=after.get("globalsObject"),
            description=after.get("description", ""),
            resource_id=after.get("_id")
        )

        # Extract event_id: unique change event ID from payload._id
        event_id = payload.get("_id", "")

        return cls(
            event_id=event_id,
            timestamp=payload.get("timestamp", log_entry["timestamp"]),
            operation=payload.get("operation", "UNKNOWN"),
            user_id=payload.get("userId", ""),
            transaction_id=payload.get("transactionId", ""),
            resource_type=resource_type,
            content=content
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for service layer communication.

        Returns clean dict without nested models for CLI consumption.
        """
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "operation": self.operation,
            "user_id": self.user_id,
            "transaction_id": self.transaction_id,
            "resource_type": self.resource_type,
            "content": {
                "type": self.content.type,
                "source": self.content.source,
                "globals": self.content.globals,
                "description": self.content.description,
                "resource_id": self.content.resource_id
            }
        }
