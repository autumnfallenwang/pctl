# ELK Service Modernization Plan

## Development Metadata
- **Phase**: Phase 2 - Service Modernization (ELK API Upgrade)
- **Target Version**: v0.5.0
- **Start Date**: 2025-09-28
- **Target Completion**: 2025-10-05 (1 week sprint)
- **Priority**: High (Technical Debt Removal)
- **Dependencies**: Connection Service Integration (v0.4.0) ✅ Complete

## Project Context
Replace Frodo subprocess dependency in ELK service with direct PAIC REST API calls, following established 3-layer architecture and domain boundary rules.

## Architecture Strategy

### Domain Boundary Rules
- `core/conn/` - ONLY accessible by `services/conn/`
- Other services access PAIC operations via ConnectionService APIs
- No cross-domain core layer access permitted

### Service Communication Flow
```
ELKService → ConnectionService.stream_logs() → core/conn/paic_api.py → PAIC REST API
TokenService → ConnectionService.get_profile() → core/conn/conn_manager.py
```

## Implementation Plan

### Phase 2.1: Extend Connection Domain (Days 1-2)
**Files to Create:**
- `pctl/core/conn/paic_api.py` - PAIC REST API operations
- `pctl/core/conn/log_models.py` - Log event data models

**Files to Modify:**
- `pctl/services/conn/conn_service.py` - Add PAIC API methods

**Implementation:**
1. Add log streaming methods to ConnectionService
2. Implement PAIC log tail endpoint with HTTPClient
3. Add log filtering and pagination support
4. Maintain Frodo-compatible behavior (5-second polling)

### Phase 2.2: Update ELK Service (Days 3-4)
**Files to Modify:**
- `pctl/services/elk/elk_service.py` - Remove Frodo, use ConnectionService
- `pctl/core/elk/streamer_process.py` - Replace subprocess with service calls

**Implementation:**
1. Replace Frodo subprocess with ConnectionService.stream_logs()
2. Add profile-based configuration to ELK commands
3. Remove direct httpx usage, use shared HTTPClient
4. Clean up unused imports (json, yaml)

### Phase 2.3: CLI Integration (Days 5-6)
**Files to Modify:**
- `pctl/cli/elk.py` - Add --profile flag support

**Implementation:**
1. Add `--profile <name>` option to all ELK commands
2. Default to first available profile or prompt user
3. Update help text and command examples
4. Maintain backward compatibility where possible

### Phase 2.4: Testing & Documentation (Day 7)
**Tasks:**
1. Test with real PAIC environments
2. Verify all ELK commands work with profiles
3. Update CLAUDE.md with completed work
4. Document new API patterns for future use

## Technical Implementation Details

### New ConnectionService Methods
```python
# Internal APIs (service-to-service)
async def stream_logs(self, profile_name: str, sources: str, level: int) -> AsyncIterator[LogEvent]
async def get_log_sources(self, profile_name: str) -> List[str]
async def validate_log_credentials(self, profile_name: str) -> bool
```

### Architecture Benefits
- **Remove Frodo dependency**: Eliminate subprocess overhead
- **Consistent patterns**: Follow established 3-layer design
- **Better error handling**: Native async/await with proper exceptions
- **Foundation for pctl log**: Enable future log commands
- **Domain integrity**: Keep PAIC logic in connection domain

## Success Criteria
- [ ] All ELK commands work without Frodo
- [ ] Profile-based log streaming functional
- [ ] No regression in existing functionality
- [ ] Clean domain boundaries maintained
- [ ] Documentation updated

## Risks & Mitigation
- **Risk**: Breaking existing ELK workflows
- **Mitigation**: Maintain same CLI interface, thorough testing

- **Risk**: Log filtering differences from Frodo
- **Mitigation**: Port exact filtering logic from Frodo examples

## Next Phase Preview
**Phase 3**: Build `pctl log` commands using established ConnectionService patterns
- Reuse PAIC API methods from connection domain
- Direct log tailing without ELK infrastructure
- Historical log search capabilities