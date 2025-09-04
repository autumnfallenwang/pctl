"""
Token-specific Pydantic models and exceptions
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator

from ..exceptions import ServiceError


class TokenConfig(BaseModel):
    """Configuration model for token generation"""
    service_account_id: str = Field(..., description="Service account identifier")
    jwk_json: str = Field(..., description="JWK as JSON string (opaque)")
    platform: str = Field(..., description="ForgeRock platform URL")
    scope: str = Field(default="fr:am:* fr:idm:*", description="OAuth scope")
    exp_seconds: int = Field(default=899, description="JWT expiration in seconds")
    proxy: Optional[str] = Field(default=None, description="Proxy configuration")
    verbose: bool = Field(default=False, description="Enable verbose logging")
    output_format: Literal["token", "bearer", "json"] = Field(default="token", description="Output format")
    verify_ssl: bool = Field(default=True, description="SSL certificate verification")
    
    @field_validator('platform')
    @classmethod
    def validate_platform_url(cls, v):
        """Ensure platform starts with https://"""
        if not v.startswith('https://'):
            raise ValueError('Platform must start with https://')
        return v
    
    @field_validator('exp_seconds')
    @classmethod
    def validate_exp_seconds(cls, v):
        """Ensure expiration is reasonable"""
        if v < 1 or v > 3600:
            raise ValueError('exp_seconds must be between 1 and 3600 seconds')
        return v


class TokenResult(BaseModel):
    """Result model for token operations"""
    token: str = Field(..., description="Access token")
    expires_in: Optional[int] = Field(default=None, description="Token expiration in seconds")
    scope: Optional[str] = Field(default=None, description="Granted scope")


class TokenResponse(BaseModel):
    """HTTP response model from token endpoint"""
    access_token: str
    token_type: str = Field(default="Bearer")
    expires_in: Optional[int] = None
    scope: Optional[str] = None


class TokenError(ServiceError):
    """Token service errors"""
    pass