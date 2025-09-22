"""
Token Service - Internal API for JWT creation and token exchange
"""

import json
import secrets
import time
from pathlib import Path
from typing import Union, Dict, Any
from loguru import logger
import jwt
from jwcrypto import jwk

from ...core.token.token_models import TokenConfig, TokenResult, TokenResponse, TokenError
from ...core.http_client import HTTPClient  
from ...core.exceptions import ConfigError
from ...core.config import ConfigLoader


class TokenService:
    """
    Service for token generation and management

    Service Layer Rules (from three-layer architecture):
    - Business logic, workflows, cross-service coordination
    - Access: core/* (shared), core/token/ (own domain), services/* (other services)
    - Communication: JSON/dict for cross-service calls (clean contracts)
    """

    def __init__(self):
        self.logger = logger
        self.config_loader = ConfigLoader()
        # Import here to avoid circular imports (service-to-service communication)
        self._connection_service = None

    @property
    def connection_service(self):
        """Lazy load ConnectionService to avoid circular imports"""
        if self._connection_service is None:
            from ..conn.conn_service import ConnectionService
            self._connection_service = ConnectionService()
        return self._connection_service
    
    def _create_signed_jwt(self, 
                          service_account_id: str,
                          audience: str, 
                          jwk_json: str,
                          exp_seconds: int = 899) -> str:
        """Create signed JWT for ForgeRock Service Account"""
        
        try:
            # Parse JWK from JSON string (treat as opaque)
            jwk_data = json.loads(jwk_json)
            
            # Convert JWK to PEM using jwcrypto (like TypeScript jwk-to-pem)
            key = jwk.JWK(**jwk_data)
            private_key_pem = key.export_to_pem(private_key=True, password=None)
            
            # Create JWT payload
            current_time = int(time.time())
            jti = secrets.token_urlsafe(16)  # Random JWT ID
            
            payload = {
                "iss": service_account_id,  # Issuer
                "sub": service_account_id,  # Subject  
                "aud": audience,            # Audience
                "exp": current_time + exp_seconds,  # Expiration
                "jti": jti                  # JWT ID
            }
            
            # Sign JWT with RSA private key PEM
            signed_jwt = jwt.encode(
                payload,
                private_key_pem,
                algorithm="RS256",
                headers={"alg": "RS256"}
            )
            
            self.logger.debug(f"Created JWT for SA={service_account_id}, exp={exp_seconds}s")
            return signed_jwt
            
        except json.JSONDecodeError as e:
            raise TokenError(f"Invalid JWK JSON format: {e}")
        except jwt.InvalidKeyError as e:
            raise TokenError(f"Invalid JWK key data: {e}")
        except Exception as e:
            raise TokenError(f"Failed to create JWT: {e}")
    
    async def get_token_from_profile(self, profile_name: str) -> Dict[str, Any]:
        """Get access token using connection profile (Service-to-service API)"""

        try:
            # Get profile from ConnectionService
            profile_result = self.connection_service.get_profile(profile_name)

            if not profile_result["success"]:
                return {
                    "success": False,
                    "error": profile_result["error"]
                }

            profile = profile_result["profile"]

            # Check if profile is validated - reject unvalidated profiles
            if not profile.get("validated", False):
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' has not been validated. Run 'pctl conn validate {profile_name}' first.",
                    "unvalidated_profile": True
                }

            # Extract token generation data from profile
            platform_url = profile["platform_url"]
            service_account_id = profile["service_account_id"]
            jwk_json = profile["service_account_jwk"]

            # Generate token using core token logic
            result = await self.get_service_account_token(
                platform_url=platform_url,
                service_account_id=service_account_id,
                jwk_json=jwk_json
            )

            return result

        except Exception as e:
            self.logger.error(f"Failed to get token from profile {profile_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_service_account_token(self, platform_url: str, service_account_id: str, jwk_json: str,
                                      scope: str = "fr:am:* fr:idm:*", exp_seconds: int = 899,
                                      verify_ssl: bool = True, proxy: str = None) -> Dict[str, Any]:
        """Get service account token (Service-to-service API for cross-service calls)"""

        try:
            # Create audience URL for token endpoint
            platform = platform_url.rstrip('/')
            audience = f"{platform}/am/oauth2/access_token"

            # Create signed JWT assertion
            signed_jwt = self._create_signed_jwt(
                service_account_id,
                audience,
                jwk_json,
                exp_seconds
            )

            # Prepare OAuth token exchange request
            form_data = {
                "client_id": "service-account",
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
                "scope": scope
            }

            # Configure HTTP client with SSL/proxy settings
            http_client = HTTPClient(
                verify_ssl=verify_ssl,
                proxy=proxy
            )

            self.logger.debug(f"Requesting access token for SA={service_account_id}")

            # Make token exchange request
            response_data = await http_client.post_form(audience, form_data)

            # Parse response
            token_response = TokenResponse(**response_data)

            self.logger.debug("✅ Access token retrieved successfully")

            return {
                "success": True,
                "token": token_response.access_token,
                "expires_in": token_response.expires_in,
                "scope": token_response.scope
            }

        except Exception as e:
            self.logger.error(f"Token request failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def validate_connection_credentials(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate connection credentials by testing token generation (For ConnectionService)"""

        try:
            platform_url = profile_data.get("platform_url")
            service_account_id = profile_data.get("service_account_id")
            jwk_json = profile_data.get("service_account_jwk")

            if not all([platform_url, service_account_id, jwk_json]):
                return {
                    "success": False,
                    "error": "Missing required credentials for validation"
                }

            # Test token generation to validate credentials
            result = await self.get_service_account_token(
                platform_url=platform_url,
                service_account_id=service_account_id,
                jwk_json=jwk_json
            )

            if result["success"]:
                return {
                    "success": True,
                    "message": "Connection credentials validated successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"Credential validation failed: {result['error']}"
                }

        except Exception as e:
            self.logger.error(f"Connection validation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_token(self, config_path: Union[str, Path]) -> TokenResult:
        """Get access token using config file (Internal API)"""
        
        try:
            # Load and validate config using ConfigLoader
            config_data = await self.config_loader.load_yaml(config_path)
            config = TokenConfig(**config_data)
            
            # Create audience URL for token endpoint
            platform = config.platform.rstrip('/')
            audience = f"{platform}/am/oauth2/access_token"
            
            # Create signed JWT assertion
            signed_jwt = self._create_signed_jwt(
                config.service_account_id,
                audience,
                config.jwk_json,
                config.exp_seconds
            )
            
            # Prepare OAuth token exchange request
            form_data = {
                "client_id": "service-account",
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", 
                "assertion": signed_jwt,
                "scope": config.scope
            }
            
            # Configure HTTP client with SSL/proxy settings
            http_client = HTTPClient(
                verify_ssl=config.verify_ssl,
                proxy=config.proxy
            )
            
            if config.verbose:
                self.logger.info(f"Requesting access token for SA={config.service_account_id}")
                self.logger.info(f"Endpoint: {audience}")
                self.logger.info(f"Scope: {config.scope}")
                self.logger.info(f"SSL verification: {config.verify_ssl}")
            
            # Make token exchange request
            response_data = await http_client.post_form(audience, form_data)
            
            # Parse response
            token_response = TokenResponse(**response_data)
            
            if config.verbose:
                self.logger.info("✅ Access token retrieved successfully")
                self.logger.info(f"   Token length: {len(token_response.access_token)}")
                self.logger.info(f"   Scope: {token_response.scope or 'N/A'}")
                self.logger.info(f"   Expires in: {token_response.expires_in or 'N/A'} seconds")
            
            return TokenResult(
                token=token_response.access_token,
                expires_in=token_response.expires_in,
                scope=token_response.scope
            )
            
        except ConfigError as e:
            raise TokenError(f"Configuration error: {e}")
        except Exception as e:
            self.logger.error(f"Token request failed: {e}")
            raise TokenError(f"Failed to get access token: {e}")
    
    def format_token(self, result: TokenResult, output_format: str = "token") -> str:
        """Format token output according to specified format"""
        
        if output_format == "token":
            return result.token
        elif output_format == "bearer":
            return f"Bearer {result.token}"
        elif output_format == "json":
            return json.dumps({
                "access_token": result.token,
                "token_type": "Bearer",
                "expires_in": result.expires_in,
                "scope": result.scope
            })
        else:
            # Default to token format
            return result.token