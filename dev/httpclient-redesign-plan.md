# HTTPClient Redesign Plan

## Metadata
- **Date**: 2025-09-28
- **Author**: Claude Code Assistant
- **Version**: 1.0
- **Priority**: High - Core Infrastructure Update
- **Impact**: Breaking change for all HTTP-dependent services
- **Estimated Effort**: 2-4 hours implementation + testing

## Executive Summary

The current `core/http_client.py` has architectural limitations that cause inconsistencies across services. Some services use our HTTPClient (returns JSON), others use raw httpx (has status codes). This redesign creates a unified, future-proof HTTP layer.

## Current Problems

### 1. **Architectural Inconsistencies**
- **ELK Service**: Uses `HTTPClient` (returns JSON directly)
- **Log Streamer**: Uses raw `httpx.AsyncClient` (has `.status_code`)
- **PAIC API**: Uses `HTTPClient._create_client()` (bypasses abstraction)

### 2. **HTTPClient Limitations**
- Only returns JSON (can't handle text responses like `_cat` endpoints)
- No access to HTTP status codes for error handling
- Missing HTTP methods (PUT, DELETE not available)
- No raw content support (binary, text, streaming)
- Poor error handling granularity

### 3. **Code Inconsistencies**
- Services check `.status_code` on JSON responses (fails)
- Inconsistent error handling patterns
- Some services bypass HTTPClient entirely

## New HTTPClient Design

### HTTPResponse Class
```python
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

    def is_success(self) -> bool:
        """Check if response is successful (2xx)"""

    def is_client_error(self) -> bool:
        """Check if response is client error (4xx)"""

    def is_server_error(self) -> bool:
        """Check if response is server error (5xx)"""

    def raise_for_status(self) -> None:
        """Raise exception for non-2xx responses"""
```

### Enhanced HTTPClient Class
```python
class HTTPClient:
    """Modern HTTP client with comprehensive response handling"""

    # Core HTTP methods
    async def get(self, url: str, headers=None, params=None) -> HTTPResponse
    async def post(self, url: str, json=None, data=None, content=None, headers=None) -> HTTPResponse
    async def put(self, url: str, json=None, data=None, headers=None) -> HTTPResponse
    async def delete(self, url: str, headers=None) -> HTTPResponse
    async def patch(self, url: str, json=None, data=None, headers=None) -> HTTPResponse

    # Convenience methods (backward compatibility)
    async def get_json(self, url: str, headers=None) -> Dict[str, Any]
    async def post_json(self, url: str, json=None, headers=None) -> Dict[str, Any]
```

### Backward Compatibility Strategy
1. **Phase 1**: Add new methods alongside existing ones
2. **Phase 2**: Update services to use new response objects
3. **Phase 3**: Remove old methods (future)

## Current HTTPClient Usage Analysis

### Services Using HTTPClient (4 services)
1. **Token Service** (`pctl/services/token/token_service.py`)
   - Usage: `post_form()` - Works with current design
   - Impact: **Low** - No changes needed

2. **Journey Service** (`pctl/services/journey/journey_service.py`)
   - Usage: `post()` for form data and JSON
   - Impact: **Low** - Uses existing methods correctly

3. **ELK Service** (`pctl/services/elk/elk_service.py`)
   - Usage: `get()`, `put()`, `post()`, `delete()`
   - **PROBLEM**: Expects `.status_code` on responses (17 locations)
   - Impact: **High** - Many status code checks need updating

4. **PAIC API** (`pctl/core/conn/paic_api.py`)
   - Usage: Bypasses HTTPClient with `._create_client()`
   - **PROBLEM**: Direct httpx usage (3 locations)
   - Impact: **Medium** - Need to use proper HTTPClient methods

### Services Using Raw httpx (2 services)
1. **Log Streamer** (`pctl/services/elk/log_streamer.py`)
   - Usage: Direct `httpx.AsyncClient` for bulk operations
   - **PROBLEM**: Should use HTTPClient for consistency
   - Impact: **High** - Complete rewrite needed

2. **Streamer Process** (`pctl/core/elk/streamer_process.py`)
   - Usage: Direct `httpx.AsyncClient`
   - **PROBLEM**: Should use HTTPClient for consistency
   - Impact: **Medium** - Update needed

## Implementation Plan

### Phase 1: Enhance HTTPClient (Non-Breaking)
1. **Add HTTPResponse class** to `core/http_client.py`
2. **Add new HTTP methods** that return HTTPResponse
3. **Keep existing methods** for backward compatibility
4. **Add convenience methods** like `get_json()` for easy migration

### Phase 2: Update Services (Breaking Changes)
1. **ELK Service**: Update all `.status_code` checks to use new response objects
2. **PAIC API**: Replace `._create_client()` calls with proper HTTPClient methods
3. **Log Streamer**: Replace httpx usage with HTTPClient
4. **Streamer Process**: Replace httpx usage with HTTPClient

### Phase 3: Testing & Validation
1. **Unit tests** for new HTTPClient methods
2. **Integration tests** for each updated service
3. **End-to-end tests** for complete workflows

## Detailed Migration Plan

### 1. ELK Service Updates (17 locations)
```python
# OLD (broken):
count_response = await self.http_client.get(url)
if count_response.status_code == 200:  # FAILS - JSON has no status_code
    data = count_response.json()

# NEW:
response = await self.http_client.get(url)
if response.is_success():
    data = response.json()
```

**Files to update:**
- `elk_service.py` lines: 380, 563, 576, 655, 715, 757, 794, 853, 874, 889
- All `.status_code` checks need response object handling

### 2. Log Streamer Updates
```python
# OLD:
self.http_client = httpx.AsyncClient(timeout=30.0)
response = await self.http_client.post(url, content=data)
if response.status_code == 200:

# NEW:
self.http_client = HTTPClient(timeout=30)
response = await self.http_client.post(url, content=data)
if response.is_success():
```

### 3. PAIC API Updates
```python
# OLD:
async with self.http_client._create_client() as client:
    response = await client.get(url)

# NEW:
response = await self.http_client.get(url)
```

## Testing Strategy

### Unit Tests
- **HTTPResponse class**: All methods and properties
- **HTTPClient methods**: Each HTTP verb with various scenarios
- **Error handling**: Network errors, HTTP errors, JSON parsing errors
- **Backward compatibility**: Existing methods still work

### Integration Tests
- **Token Service**: No changes expected
- **Journey Service**: No changes expected
- **ELK Service**: All Elasticsearch operations
- **Log Streamer**: Bulk indexing and template operations

### End-to-End Tests
- **ELK workflow**: `init → start → status → stop → clean → purge`
- **Journey workflow**: Complete authentication flow
- **Connection validation**: Profile validation with HTTP calls

## Risk Assessment

### High Risk
- **ELK Service**: 17 status code checks need updating
- **Log Streamer**: Complete HTTP client replacement

### Medium Risk
- **PAIC API**: Bypasses current abstraction
- **Streamer Process**: Uses raw httpx

### Low Risk
- **Token Service**: Uses existing working methods
- **Journey Service**: Uses existing working methods

## Rollback Plan

1. **Git branch**: Create feature branch for all changes
2. **Incremental commits**: Each service update in separate commit
3. **Keep old methods**: Don't remove until testing complete
4. **Easy revert**: Can revert individual service updates

## Success Criteria

1. **All services use HTTPClient**: No raw httpx usage
2. **Status code access works**: Services can check HTTP status
3. **All HTTP methods available**: GET, POST, PUT, DELETE, PATCH
4. **Non-JSON responses supported**: Text, binary content handling
5. **Backward compatibility maintained**: Existing code continues working
6. **Tests pass**: Unit, integration, and e2e tests successful

## Post-Implementation Tasks

1. **Documentation update**: Update HTTPClient usage examples
2. **Code review**: Ensure consistent patterns across services
3. **Performance testing**: Verify no performance regression
4. **Future cleanup**: Remove deprecated methods in next version

---

## Next Steps

1. **Review and approve** this plan
2. **Implement Phase 1**: Enhanced HTTPClient with new methods
3. **Update services**: Migrate each service to new response objects
4. **Test thoroughly**: Validate all functionality works
5. **Document changes**: Update developer documentation

This redesign establishes HTTPClient as the definitive HTTP layer for current and future pctl services.