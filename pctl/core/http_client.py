"""
HTTP client utilities using httpx with SSL/proxy support
"""

import httpx
import ssl
from typing import Optional, Dict, Any
from loguru import logger
from .exceptions import ServiceError


class HTTPClient:
    """Modern HTTP client with SSL and proxy support"""
    
    def __init__(self, 
                 timeout: int = 30, 
                 verify_ssl: bool = True,
                 proxy: Optional[str] = None):
        self.timeout = timeout
        self.verify_ssl = verify_ssl  
        self.proxy = proxy
        self.logger = logger
    
    def _create_client(self) -> httpx.AsyncClient:
        """Create configured httpx client"""
        
        # SSL verification settings
        if not self.verify_ssl:
            # Disable SSL verification (like Python requests verify=False)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            verify = ssl_context
        else:
            verify = True
            
        # Client configuration
        client_kwargs = {
            "timeout": self.timeout,
            "verify": verify,
            "headers": {"User-Agent": "pctl/0.1.0"}
        }
        
        # Proxy configuration (httpx uses 'proxy' not 'proxies')
        if self.proxy:
            client_kwargs["proxy"] = self.proxy
        
        return httpx.AsyncClient(**client_kwargs)
    
    async def post_form(self, 
                       url: str, 
                       data: Dict[str, str],
                       headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """POST form data (application/x-www-form-urlencoded)"""
        
        default_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            default_headers.update(headers)
            
        try:
            async with self._create_client() as client:
                self.logger.debug(f"POST {url}")
                
                response = await client.post(
                    url,
                    data=data,
                    headers=default_headers
                )
                
                response.raise_for_status()
                
                # Return JSON response
                return response.json()
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.logger.error(f"HTTP error for {url}: {error_msg}")
            raise ServiceError(f"HTTP request failed: {error_msg}")
            
        except httpx.RequestError as e:
            error_msg = f"Request error: {str(e)}"
            self.logger.error(f"Request error for {url}: {error_msg}")
            raise ServiceError(f"Network error: {error_msg}")
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error for {url}: {error_msg}")
            raise ServiceError(error_msg)
    
    async def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """GET request returning JSON"""
        
        try:
            async with self._create_client() as client:
                self.logger.debug(f"GET {url}")
                
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                return response.json()
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.logger.error(f"HTTP error for {url}: {error_msg}")
            raise ServiceError(f"HTTP request failed: {error_msg}")
            
        except httpx.RequestError as e:
            error_msg = f"Request error: {str(e)}"
            self.logger.error(f"Request error for {url}: {error_msg}")
            raise ServiceError(f"Network error: {error_msg}")
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error for {url}: {error_msg}")
            raise ServiceError(error_msg)
    
    async def post(self, url: str, json: Optional[Dict[str, Any]] = None, 
                  params: Optional[Dict[str, str]] = None,
                  headers: Optional[Dict[str, str]] = None,
                  timeout: Optional[float] = None) -> Dict[str, Any]:
        """POST request with JSON payload"""
        
        try:
            async with self._create_client() as client:
                self.logger.debug(f"POST {url}")
                
                response = await client.post(
                    url,
                    json=json,
                    params=params,
                    headers=headers,
                    timeout=timeout or self.timeout
                )
                
                response.raise_for_status()
                
                return response.json()
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.logger.error(f"HTTP error for {url}: {error_msg}")
            raise ServiceError(f"HTTP request failed: {error_msg}")
            
        except httpx.RequestError as e:
            error_msg = f"Request error: {str(e)}"
            self.logger.error(f"Request error for {url}: {error_msg}")
            raise ServiceError(f"Network error: {error_msg}")
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error for {url}: {error_msg}")
            raise ServiceError(error_msg)