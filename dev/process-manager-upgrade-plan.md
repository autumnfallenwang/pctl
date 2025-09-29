# ProcessManager Upgrade Plan - Unified Process Management

> **Comprehensive plan to replace subprocess_runner with modern, unified ProcessManager**

## Current State Analysis

### Problems with Current Architecture

**pctl/core/subprocess_runner.py Issues:**
- ❌ **CLI-only design** - forces fake internal CLIs with argparse
- ❌ **Mixed sync/async** - background processes use sync subprocess.Popen
- ❌ **PID-only tracking** - fragile, no metadata, PID reuse issues
- ❌ **Limited process types** - only external CLI commands
- ❌ **Manual lifecycle** - no unified start/stop/monitor interface
- ❌ **Inconsistent error handling** - different patterns for different operations

**Current Usage Patterns:**
```python
# ELK Service currently does:
subprocess_runner.run_command(["docker", "ps", "-a"])  # ✅ Works well

# But forces this ugly pattern:
streamer_cmd = [sys.executable, "-m", "pctl.services.elk.log_streamer",
                "--profile-name", profile, "--source", source, ...]
pid = subprocess_runner.start_background_process_simple(streamer_cmd, log_file)

# Which requires log_streamer.py to have fake argparse CLI ❌
```

### Impact Analysis

**Files Currently Using subprocess_runner:**
- `pctl/services/elk/elk_service.py` - Docker commands + streamer launching
- `pctl/services/elk/streamer_manager.py` - Process lifecycle management
- Any future services needing background processes

**Migration Complexity:**
- **High** - Core foundational change affecting multiple services
- **Breaking** - Will change APIs across service layer
- **Beneficial** - Eliminates architectural debt and enables clean patterns

## Target Architecture

### ProcessManager Design

**Core Module:** `pctl/core/process_manager.py`

```python
from typing import Union, Callable, Any, Optional, List, Dict
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from pathlib import Path
import asyncio
from concurrent.futures import ProcessPoolExecutor

class ProcessType(str, Enum):
    """Types of processes managed by ProcessManager"""
    CLI_COMMAND = "cli_command"          # External CLI tools (docker, curl, etc.)
    PYTHON_FUNCTION = "python_function"  # Python callables in subprocess
    ASYNC_TASK = "async_task"           # Asyncio tasks (in-process)

class ProcessStatus(str, Enum):
    """Process lifecycle states"""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass
class ProcessHandle:
    """Unified process identifier with rich metadata"""
    handle_id: str                        # Primary identifier (UUID or semantic name)
    process_type: ProcessType             # Type of process
    created_at: datetime                  # Creation timestamp
    command_or_func: str                  # Human readable description

    # Platform-specific control objects
    pid: Optional[int] = None             # OS PID when available
    process_obj: Optional[Any] = None     # subprocess.Popen, multiprocessing.Process
    future_obj: Optional[Any] = None      # concurrent.futures.Future
    task_obj: Optional[asyncio.Task] = None  # asyncio.Task

    # Runtime configuration
    log_file: Optional[Path] = None       # Process log file
    working_dir: Optional[Path] = None    # Working directory
    env_vars: Optional[Dict[str, str]] = None  # Environment variables

    # Current state
    status: ProcessStatus = ProcessStatus.STARTING
    exit_code: Optional[int] = None
    last_updated: datetime = None

@dataclass
class ProcessResult:
    """Result of completed process execution"""
    handle: ProcessHandle
    stdout: str
    stderr: str
    exit_code: int
    success: bool
    duration_seconds: float

class ProcessManager:
    """Modern unified process management for CLI and Python processes"""

    def __init__(self, registry_file: Optional[Path] = None):
        self.registry_file = registry_file or Path.home() / ".pctl" / "processes.json"
        self.processes: Dict[str, ProcessHandle] = {}
        self.executor = ProcessPoolExecutor(max_workers=4)
        self.logger = logger

    # ==========================================
    # External CLI Processes
    # ==========================================

    async def run_cli(self,
                     cmd: List[str],
                     timeout: int = 300,
                     cwd: Optional[Path] = None,
                     env: Optional[Dict[str, str]] = None) -> ProcessResult:
        """Run CLI command and wait for completion"""

    async def start_cli_background(self,
                                  cmd: List[str],
                                  handle_id: Optional[str] = None,
                                  log_file: Optional[Path] = None,
                                  cwd: Optional[Path] = None,
                                  env: Optional[Dict[str, str]] = None) -> ProcessHandle:
        """Start CLI command as background process"""

    # ==========================================
    # Python Function Processes
    # ==========================================

    async def run_python(self,
                         func: Callable,
                         *args,
                         timeout: Optional[int] = None,
                         **kwargs) -> Any:
        """Run Python function in subprocess and return result"""

    async def start_python_background(self,
                                     func: Callable,
                                     *args,
                                     handle_id: Optional[str] = None,
                                     log_file: Optional[Path] = None,
                                     **kwargs) -> ProcessHandle:
        """Start Python function as background subprocess"""

    # ==========================================
    # Async Task Processes (in-process)
    # ==========================================

    async def start_async_task(self,
                              coro: Callable,
                              *args,
                              handle_id: Optional[str] = None,
                              **kwargs) -> ProcessHandle:
        """Start async coroutine as managed task"""

    # ==========================================
    # Unified Process Control
    # ==========================================

    async def stop_process(self, handle_id: str, force: bool = False) -> bool:
        """Stop process gracefully (SIGTERM) or forcefully (SIGKILL)"""

    async def get_status(self, handle_id: str) -> ProcessStatus:
        """Get current process status"""

    async def get_handle(self, handle_id: str) -> Optional[ProcessHandle]:
        """Get process handle by ID"""

    async def list_processes(self,
                           process_type: Optional[ProcessType] = None,
                           status: Optional[ProcessStatus] = None) -> List[ProcessHandle]:
        """List processes with optional filtering"""

    async def wait_for_process(self, handle_id: str, timeout: Optional[int] = None) -> ProcessResult:
        """Wait for process completion"""

    # ==========================================
    # Registry Management
    # ==========================================

    async def save_registry(self) -> None:
        """Persist process registry to disk"""

    async def load_registry(self) -> None:
        """Load process registry from disk"""

    async def cleanup_dead_processes(self) -> int:
        """Remove dead processes from registry"""
```

### Key Design Principles

1. **Unified Interface** - Same methods work for CLI commands, Python functions, and async tasks
2. **Handle-based Identity** - Stable, semantic identifiers instead of just PIDs
3. **Async-first** - All operations return awaitables
4. **Rich Metadata** - Full context about what each process does
5. **Graceful Degradation** - Handle missing PIDs, dead processes gracefully
6. **Extensible** - Easy to add new process types in future

### Usage Examples

```python
pm = ProcessManager()

# External CLI (replaces current subprocess_runner)
result = await pm.run_cli(["docker", "ps", "-a"])
handle = await pm.start_cli_background(
    ["docker", "run", "-d", "nginx"],
    handle_id="nginx-server",
    log_file=Path("nginx.log")
)

# Python functions (eliminates fake CLI patterns)
handle = await pm.start_python_background(
    streamer.start_streaming,
    profile_name="myenv",
    config=config,
    handle_id="elk-streamer-myenv",
    log_file=Path("elk-myenv.log")
)

# Async tasks (new capability)
handle = await pm.start_async_task(
    monitor_health_checks,
    interval=30,
    handle_id="health-monitor"
)

# Unified control
await pm.stop_process("elk-streamer-myenv")
status = await pm.get_status("nginx-server")
processes = await pm.list_processes(status=ProcessStatus.RUNNING)
```

## Migration Strategy

### Phase 1: Core Implementation (Week 1)

**1.1 Build ProcessManager Core**
- [ ] Implement `pctl/core/process_manager.py` with full API
- [ ] Add comprehensive unit tests
- [ ] Add integration tests with real subprocesses
- [ ] Document API with examples

**1.2 Registry System**
- [ ] Implement JSON-based process registry
- [ ] Add registry persistence and loading
- [ ] Add cleanup utilities for dead processes
- [ ] Handle registry corruption gracefully

### Phase 2: ELK Service Migration (Week 2)

**2.1 Update ELK Service**
- [ ] Replace `subprocess_runner` imports with `ProcessManager`
- [ ] Convert Docker command calls to `pm.run_cli()`
- [ ] Convert streamer launching to `pm.start_python_background()`
- [ ] Update error handling patterns

**2.2 Eliminate Fake CLI**
- [ ] Remove argparse from `log_streamer.py`
- [ ] Convert to direct function calls
- [ ] Update StreamerManager to use handles instead of PIDs
- [ ] Test all ELK commands end-to-end

**2.3 Update Models**
- [ ] Add handle_id to StreamerStatus model
- [ ] Update registry schema for new handle format
- [ ] Migrate existing PID-based data if present

### Phase 3: Validation & Cleanup (Week 3)

**3.1 Comprehensive Testing**
- [ ] Test all ELK commands with new ProcessManager
- [ ] Test process lifecycle (start/stop/status/cleanup)
- [ ] Test registry persistence across restarts
- [ ] Test error conditions and edge cases

**3.2 Remove Legacy Code**
- [ ] Delete `pctl/core/subprocess_runner.py`
- [ ] Remove subprocess_runner imports across codebase
- [ ] Update any remaining direct subprocess usage
- [ ] Clean up unused CLI argument patterns

**3.3 Documentation Update**
- [ ] Update CLAUDE.md with new architecture
- [ ] Add ProcessManager usage examples
- [ ] Document migration path for future services

### Phase 4: Future Enablement (Week 4)

**4.1 Service Integration**
- [ ] Add ProcessManager to other services as needed
- [ ] Consider shared process monitoring utilities
- [ ] Add process health checking capabilities

**4.2 Advanced Features**
- [ ] Process resource monitoring (CPU, memory)
- [ ] Process restart policies and auto-recovery
- [ ] Process dependency management
- [ ] Structured logging with correlation IDs

## Impact Assessment

### Benefits

**🎯 Direct Problem Resolution:**
- ✅ **Eliminates fake CLIs** - direct Python function calls
- ✅ **Modern async patterns** - consistent await/async throughout
- ✅ **Rich process metadata** - debuggable, maintainable
- ✅ **Unified interface** - same API for all process types
- ✅ **Stable identifiers** - semantic handles vs fragile PIDs

**🚀 Future Capabilities Enabled:**
- ✅ **Easy service scaling** - background Python processes made simple
- ✅ **Process monitoring** - comprehensive status and health tracking
- ✅ **Operational debugging** - rich logs with process context
- ✅ **Cross-service coordination** - processes can discover and interact

**🔧 Technical Improvements:**
- ✅ **Better error handling** - structured exceptions with context
- ✅ **Resource management** - proper cleanup and lifecycle management
- ✅ **Testing improvements** - mockable, testable process management
- ✅ **Code reduction** - eliminate subprocess boilerplate across services

### Risks & Mitigation

**⚠️ Complexity Risk:**
- **Risk**: ProcessManager is complex, could introduce bugs
- **Mitigation**: Comprehensive testing, gradual rollout, fallback plans

**⚠️ Breaking Changes:**
- **Risk**: ELK service APIs change, existing workflows break
- **Mitigation**: Maintain backward compatibility where possible, clear migration docs

**⚠️ Performance Impact:**
- **Risk**: Additional abstraction could slow down process operations
- **Mitigation**: Benchmark before/after, optimize hot paths

### Success Metrics

**📊 Measurable Improvements:**
- **Code reduction**: Lines of subprocess boilerplate eliminated
- **API consistency**: All process operations use same interface patterns
- **Error clarity**: Structured errors with process context
- **Development velocity**: Time to add new background processes

**🎯 Functional Validation:**
- **All ELK commands work identically** - no user-visible changes
- **Process reliability improves** - better startup/shutdown handling
- **Debugging experience improves** - richer logs and status info

## Implementation Timeline

```
Week 1: Core ProcessManager implementation + tests
Week 2: ELK service migration + fake CLI elimination
Week 3: Validation + legacy code removal
Week 4: Documentation + future feature enablement

Total: ~4 weeks for complete migration
```

## File Changes Summary

**New Files:**
- `pctl/core/process_manager.py` - Main ProcessManager implementation
- `tests/test_process_manager.py` - Comprehensive test suite
- `dev/process-manager-upgrade-plan.md` - This planning document

**Modified Files:**
- `pctl/services/elk/elk_service.py` - Replace subprocess_runner usage
- `pctl/services/elk/streamer_manager.py` - Use handles instead of PIDs
- `pctl/services/elk/log_streamer.py` - Remove argparse, convert to functions
- `pctl/core/elk/elk_models.py` - Add handle_id fields where needed

**Deleted Files:**
- `pctl/core/subprocess_runner.py` - Replaced by ProcessManager

**Registry Changes:**
- `~/.pctl/processes.json` - New unified process registry format
- `~/.pctl/streamers.json` - Migrate to new format or merge into processes.json

## Next Steps

1. **Review and approve this plan** - Ensure architectural direction is correct
2. **Create implementation branch** - `feature/process-manager-unified`
3. **Start with ProcessManager core** - Get the foundation solid first
4. **Incremental testing** - Validate each component before moving forward
5. **Document lessons learned** - Update patterns for future services

---

**This migration will establish ProcessManager as the new foundation for all process management in pctl, eliminating technical debt and enabling modern async patterns throughout the codebase.**