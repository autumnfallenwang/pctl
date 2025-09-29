"""
HTTP client utilities using httpx with SSL/proxy support
Enhanced with rich response objects and comprehensive HTTP method support
"""

import httpx
import ssl
import json as json_module
from typing import Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger
from .exceptions import ServiceError


@dataclass
class HTTPResponse:
    """Rich response object providing access to all response data"""
    status_code: int
    headers: Dict[str, str]
    text: str
    content: bytes
    url: str

    def json(self) -> Dict[str, Any]:
        """Parse response as JSON"""
        try:
            return json_module.loads(self.text)
        except json_module.JSONDecodeError as e:
            raise ServiceError(f"Failed to parse JSON response: {e}")

    def is_success(self) -> bool:
        """Check if response is successful (2xx)"""
        return 200 <= self.status_code < 300

    def is_client_error(self) -> bool:
        """Check if response is client error (4xx)"""
        return 400 <= self.status_code < 500

    def is_server_error(self) -> bool:
        """Check if response is server error (5xx)"""
        return 500 <= self.status_code < 600

    def raise_for_status(self) -> None:
        """Raise exception for non-2xx responses"""
        if not self.is_success():
            error_msg = f"HTTP {self.status_code}: {self.text}"
            raise ServiceError(f"HTTP request failed: {error_msg}")


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

    # ==============================================================================
    # ENHANCED HTTP METHODS (return HTTPResponse objects)
    # ==============================================================================

    async def _make_request(self, method: str, url: str, **kwargs) -> HTTPResponse:
        """Internal method to make HTTP requests and return HTTPResponse"""
        try:
            async with self._create_client() as client:
                self.logger.debug(f"{method.upper()} {url}")

                response = await client.request(method, url, **kwargs)

                # Convert httpx.Response to HTTPResponse
                return HTTPResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    text=response.text,
                    content=response.content,
                    url=str(response.url)
                )

        except httpx.RequestError as e:
            error_msg = f"Request error: {str(e)}"
            self.logger.error(f"Request error for {url}: {error_msg}")
            raise ServiceError(f"Network error: {error_msg}")

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error for {url}: {error_msg}")
            raise ServiceError(error_msg)

    async def get_response(self, url: str, headers: Optional[Dict[str, str]] = None,
                          params: Optional[Dict[str, str]] = None) -> HTTPResponse:
        """GET request returning HTTPResponse object"""
        return await self._make_request("GET", url, headers=headers, params=params)

    async def post_response(self, url: str, json: Optional[Dict[str, Any]] = None,
                           data: Optional[Dict[str, Any]] = None,
                           content: Optional[bytes] = None,
                           headers: Optional[Dict[str, str]] = None,
                           params: Optional[Dict[str, str]] = None,
                           timeout: Optional[float] = None) -> HTTPResponse:
        """POST request returning HTTPResponse object"""
        kwargs = {"headers": headers, "params": params}
        if timeout:
            kwargs["timeout"] = timeout
        if json is not None:
            kwargs["json"] = json
        elif data is not None:
            kwargs["data"] = data
        elif content is not None:
            kwargs["content"] = content

        return await self._make_request("POST", url, **kwargs)

    async def put_response(self, url: str, json: Optional[Dict[str, Any]] = None,
                          data: Optional[Dict[str, Any]] = None,
                          headers: Optional[Dict[str, str]] = None) -> HTTPResponse:
        """PUT request returning HTTPResponse object"""
        kwargs = {"headers": headers}
        if json is not None:
            kwargs["json"] = json
        elif data is not None:
            kwargs["data"] = data

        return await self._make_request("PUT", url, **kwargs)

    async def delete_response(self, url: str, headers: Optional[Dict[str, str]] = None) -> HTTPResponse:
        """DELETE request returning HTTPResponse object"""
        return await self._make_request("DELETE", url, headers=headers)

    async def patch_response(self, url: str, json: Optional[Dict[str, Any]] = None,
                            data: Optional[Dict[str, Any]] = None,
                            headers: Optional[Dict[str, str]] = None) -> HTTPResponse:
        """PATCH request returning HTTPResponse object"""
        kwargs = {"headers": headers}
        if json is not None:
            kwargs["json"] = json
        elif data is not None:
            kwargs["data"] = data

        return await self._make_request("PATCH", url, **kwargs)

    # ==============================================================================
    # CONVENIENCE METHODS (for easy migration and common use cases)
    # ==============================================================================

    async def get_json(self, url: str, headers: Optional[Dict[str, str]] = None,
                      params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """GET request returning JSON data directly"""
        response = await self.get_response(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    async def post_json(self, url: str, json: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """POST request returning JSON data directly"""
        response = await self.post_response(url, json=json, headers=headers)
        response.raise_for_status()
        return response.json()

    async def put_json(self, url: str, json: Optional[Dict[str, Any]] = None,
                      headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """PUT request returning JSON data directly"""
        response = await self.put_response(url, json=json, headers=headers)
        response.raise_for_status()
        return response.json()

    async def delete_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """DELETE request returning JSON data directly"""
        response = await self.delete_response(url, headers=headers)
        response.raise_for_status()
        return response.json()