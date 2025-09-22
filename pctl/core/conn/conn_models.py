"""
Connection configuration models
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class ConnectionProfile:
    """Environment connection profile"""
    # Required fields
    platform_url: str  # Primary platform URL (required)
    service_account_id: str  # Service account ID (required)
    service_account_jwk: str  # Service account JWK (required)

    # Optional fields (auto-generated or user-provided)
    name: Optional[str] = None  # Profile name (unique key, auto-gen from platform_url if not provided)
    log_api_key: Optional[str] = None  # Log API key (prompt when needed)
    log_api_secret: Optional[str] = None  # Log API secret (prompt when needed)
    admin_username: Optional[str] = None  # Admin username (optional)
    admin_password: Optional[str] = None  # Admin password (optional)
    description: Optional[str] = None  # User description
    validated: bool = False  # Whether credentials have been validated

    def __post_init__(self):
        """Post-initialization validation and auto-generation"""
        # Auto-generate name from platform_url if not provided
        if not self.name:
            self.name = self._generate_name_from_url(self.platform_url)

        # Validate required fields
        if not self.platform_url:
            raise ValueError("platform_url is required")
        if not self.service_account_id:
            raise ValueError("service_account_id is required")
        if not self.service_account_jwk:
            raise ValueError("service_account_jwk is required")

    def _generate_name_from_url(self, url: str) -> str:
        """Generate profile name from platform URL (just use the URL as-is)"""
        return url

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionProfile":
        """Create profile from dictionary"""
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    def get_log_auth_headers(self) -> Dict[str, str]:
        """Get headers for log API authentication"""
        if not self.log_api_key or not self.log_api_secret:
            raise ValueError(f"Log API credentials not configured for profile '{self.name}'. "
                           f"Please configure log_api_key and log_api_secret.")

        return {
            'x-api-key': self.log_api_key,
            'x-api-secret': self.log_api_secret
        }

    def has_log_credentials(self) -> bool:
        """Check if profile has log API credentials"""
        return bool(self.log_api_key and self.log_api_secret)

    def has_service_account_credentials(self) -> bool:
        """Check if profile has service account credentials (always true for valid profiles)"""
        return bool(self.service_account_id and self.service_account_jwk)

    def has_admin_credentials(self) -> bool:
        """Check if profile has admin credentials"""
        return bool(self.admin_username and self.admin_password)

    def get_base_url(self) -> str:
        """Get base URL (alias for platform_url for backward compatibility)"""
        return self.platform_url

    def is_validated(self) -> bool:
        """Check if profile credentials have been validated"""
        return self.validated

    def mark_validated(self) -> None:
        """Mark profile as validated"""
        self.validated = True

    def mark_unvalidated(self) -> None:
        """Mark profile as unvalidated"""
        self.validated = False