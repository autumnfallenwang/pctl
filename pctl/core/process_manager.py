"""
Unified process manager for both background and run-wait scenarios.

This module provides a unified interface for process execution:

FLOW 1 - Background (start and return immediately):
  - start_background() - Unified interface for both CLI and Python functions
  - Returns ProcessHandle with PID
  - Process continues running independently

FLOW 2 - Run and Wait (execute and wait for completion):
  - run_and_wait() - Unified interface for both CLI and Python functions
  - Returns CommandResult with stdout/stderr/returncode
  - Blocks until process completes

Core responsibility: Process execution only
Service layer responsibility: Process tracking/registry (e.g., StreamerManager)
"""

import asyncio
import os
import signal
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from loguru import logger


@dataclass
class ProcessHandle:
    """Handle to control a background process.

    Contains minimal information needed to control and monitor
    a background process. Service layer decides how to persist/track these.
    """
    pid: int                                # OS process ID
    command_or_func: str                    # Human-readable description
    log_file: Optional[Path] = None         # Log file path
    process_obj: Optional[Any] = None       # subprocess.Popen or Process object


@dataclass
class CommandResult:
    """Result of a completed command execution."""
    stdout: str
    stderr: str
    returncode: int
    success: bool


class ProcessManager:
    """
    Unified process manager for CLI commands and Python functions.

    Handles two execution flows:
    1. Background: Start process and return immediately (Flow 1)
    2. Run-and-wait: Execute and wait for completion (Flow 2)

    Example usage:
        pm = ProcessManager()

        # Flow 1: Background processes
        handle = pm.start_background(
            func=run_streamer_process,
            profile_name="env1",
            source="idm-core",
            log_file=Path("streamer.log")
        )
        # or
        handle = pm.start_background(
            cmd=["docker", "run", "-d", "nginx"],
            log_file=Path("docker.log")
        )

        # Flow 2: Run and wait
        result = await pm.run_and_wait(cmd=["docker", "ps", "-a"])
        # or
        result = await pm.run_and_wait(
            func=some_function,
            arg1="value1",
            arg2="value2"
        )
    """

    def __init__(self):
        """Initialize process manager."""
        self.executor = ProcessPoolExecutor(max_workers=4)
        self.logger = logger

    # ==========================================
    # FLOW 1: Background (start and return)
    # ==========================================

    def start_background(
        self,
        cmd: Optional[List[str]] = None,
        func: Optional[Callable] = None,
        log_file: Optional[Path] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> ProcessHandle:
        """
        Start process in background and return immediately (FLOW 1).

        Unified interface for both CLI commands and Python functions.
        Provide EITHER cmd OR func, not both.

        Args:
            cmd: CLI command and arguments (e.g., ["docker", "run", "-d", "nginx"])
            func: Python function to execute (e.g., run_streamer_process)
            log_file: Optional log file for stdout/stderr
            cwd: Working directory (CLI only)
            env: Environment variables (CLI only)
            **kwargs: Arguments for Python function (func only)

        Returns:
            ProcessHandle with PID for process control

        Example:
            # CLI command
            handle = pm.start_background(
                cmd=["sleep", "60"],
                log_file=Path("sleep.log")
            )

            # Python function
            handle = pm.start_background(
                func=run_streamer_process,
                profile_name="env1",
                source="idm-core",
                log_file=Path("streamer.log")
            )
        """
        if cmd and func:
            raise ValueError("Provide either cmd or func, not both")
        if not cmd and not func:
            raise ValueError("Must provide either cmd or func")

        if cmd:
            return self._start_cli_background(cmd, log_file, cwd, env)
        else:
            return self._start_python_background(func, log_file, **kwargs)

    def _start_python_background(
        self,
        func: Callable,
        log_file: Optional[Path] = None,
        **kwargs
    ) -> ProcessHandle:
        """Start Python function as background process.

        Uses python -c to directly invoke the function without requiring
        argparse or __main__ setup in the target module.

        Process truly detaches from parent (survives parent exit) using:
        - subprocess.Popen with os.setsid
        - Direct function invocation via python -c
        """
        func_module = func.__module__
        func_name = func.__name__

        # Build function call arguments as Python repr strings
        args_parts = []
        for key, value in kwargs.items():
            # Skip None values
            if value is None:
                continue
            # Represent value as Python literal
            args_parts.append(f"{key}={repr(value)}")

        # Add log file if specified
        if log_file:
            # Configure loguru to output to file before calling function
            log_setup = f"from loguru import logger; logger.add({repr(str(log_file))}, rotation='10 MB', retention='7 days'); "
        else:
            log_setup = ""

        # Build the Python script
        args_str = ", ".join(args_parts)
        python_script = (
            f"import sys; "
            f"{log_setup}"
            f"from {func_module} import {func_name}; "
            f"{func_name}({args_str})"
        )

        # Construct the command: python -c "script"
        cmd = [sys.executable, "-c", python_script]

        # Prepare stdout/stderr
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            stdout_fd = open(log_file, 'a')
            stderr_fd = subprocess.STDOUT
        else:
            stdout_fd = subprocess.DEVNULL
            stderr_fd = subprocess.DEVNULL

        # Start process with new session (fully detached)
        process = subprocess.Popen(
            cmd,
            stdout=stdout_fd,
            stderr=stderr_fd,
            preexec_fn=os.setsid  # Create new process group - survives parent
        )

        # Create handle
        func_desc = f"{func_module}.{func_name}"
        handle = ProcessHandle(
            pid=process.pid,
            command_or_func=func_desc,
            log_file=log_file,
            process_obj=None
        )

        self.logger.info(f"Started Python background process: {func_desc} (PID: {process.pid})")

        return handle

    def _start_cli_background(
        self,
        cmd: List[str],
        log_file: Optional[Path] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None
    ) -> ProcessHandle:
        """Start CLI command as background process."""
        # Prepare environment
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        # Prepare stdout/stderr
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            stdout_fd = open(log_file, 'a')
            stderr_fd = subprocess.STDOUT
        else:
            stdout_fd = subprocess.DEVNULL
            stderr_fd = subprocess.DEVNULL

        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=stdout_fd,
            stderr=stderr_fd,
            cwd=cwd,
            env=process_env,
            preexec_fn=os.setsid  # Create new process group
        )

        # Create handle
        handle = ProcessHandle(
            pid=process.pid,
            command_or_func=" ".join(cmd),
            log_file=log_file,
            process_obj=process
        )

        self.logger.info(f"Started CLI background process: {' '.join(cmd)} (PID: {process.pid})")

        return handle

    # ==========================================
    # FLOW 2: Run and Wait (execute and wait)
    # ==========================================

    async def run_and_wait(
        self,
        cmd: Optional[List[str]] = None,
        func: Optional[Callable] = None,
        cwd: Optional[Path] = None,
        timeout: int = 300,
        **kwargs
    ) -> CommandResult:
        """
        Run process and wait for completion (FLOW 2).

        Unified interface for both CLI commands and Python functions.
        Provide EITHER cmd OR func, not both.

        Args:
            cmd: CLI command and arguments (e.g., ["docker", "ps", "-a"])
            func: Python function to execute
            cwd: Working directory (CLI only)
            timeout: Timeout in seconds
            **kwargs: Arguments for Python function (func only)

        Returns:
            CommandResult with stdout, stderr, returncode, success

        Example:
            # CLI command
            result = await pm.run_and_wait(cmd=["docker", "ps"])
            if result.success:
                print(result.stdout)

            # Python function
            result = await pm.run_and_wait(
                func=some_calculation,
                x=10,
                y=20
            )
        """
        if cmd and func:
            raise ValueError("Provide either cmd or func, not both")
        if not cmd and not func:
            raise ValueError("Must provide either cmd or func")

        if cmd:
            return await self._run_cli_and_wait(cmd, cwd, timeout)
        else:
            return await self._run_python_and_wait(func, timeout, **kwargs)

    async def _run_cli_and_wait(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        timeout: int = 300
    ) -> CommandResult:
        """Run CLI command and wait for completion."""
        try:
            self.logger.debug(f"Running command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise TimeoutError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

            result = CommandResult(
                stdout=stdout.decode('utf-8', errors='replace') if stdout else "",
                stderr=stderr.decode('utf-8', errors='replace') if stderr else "",
                returncode=process.returncode,
                success=process.returncode == 0
            )

            if not result.success:
                self.logger.error(f"Command failed: {' '.join(cmd)}")
                self.logger.error(f"Exit code: {result.returncode}")
                self.logger.error(f"stderr: {result.stderr}")

            return result

        except FileNotFoundError:
            raise FileNotFoundError(f"Command not found: {cmd[0]}")

    async def _run_python_and_wait(
        self,
        func: Callable,
        timeout: Optional[int] = None,
        **kwargs
    ) -> CommandResult:
        """Run Python function and wait for completion."""
        try:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                self.executor,
                func,
                **kwargs
            )

            if timeout:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future

            # Python functions don't have stdout/stderr like CLI
            # Return result as stdout
            return CommandResult(
                stdout=str(result),
                stderr="",
                returncode=0,
                success=True
            )

        except Exception as e:
            self.logger.error(f"Python function failed: {e}")
            return CommandResult(
                stdout="",
                stderr=str(e),
                returncode=1,
                success=False
            )

    # ==========================================
    # Process Control (for background processes)
    # ==========================================

    def stop_process(self, handle: ProcessHandle, force: bool = False, timeout: int = 10) -> bool:
        """
        Stop background process gracefully (SIGTERM) or forcefully (SIGKILL).

        Args:
            handle: ProcessHandle returned from start_background()
            force: Use SIGKILL immediately if True
            timeout: Seconds to wait before force kill (if force=False)

        Returns:
            True if process was stopped, False if already dead or error
        """
        try:
            # Check if process exists
            try:
                os.kill(handle.pid, 0)
            except OSError:
                self.logger.debug(f"Process {handle.pid} already dead")
                return False

            if force:
                # Immediate force kill
                os.kill(handle.pid, signal.SIGKILL)
                self.logger.info(f"Force killed process {handle.pid}")
                return True

            # Graceful shutdown
            os.kill(handle.pid, signal.SIGTERM)
            self.logger.debug(f"Sent SIGTERM to process {handle.pid}")

            # Wait for process to stop
            import time
            for _ in range(timeout):
                try:
                    os.kill(handle.pid, 0)
                    time.sleep(1)
                except OSError:
                    self.logger.info(f"Process {handle.pid} stopped gracefully")
                    return True

            # Force kill if still running
            self.logger.warning(f"Process {handle.pid} didn't stop gracefully, force killing")
            os.kill(handle.pid, signal.SIGKILL)
            return True

        except Exception as e:
            self.logger.error(f"Error stopping process {handle.pid}: {e}")
            return False

    def stop_process_by_pid(self, pid: int, force: bool = False, timeout: int = 10) -> bool:
        """
        Stop process by PID (convenience method).

        Args:
            pid: Process ID
            force: Use SIGKILL immediately if True
            timeout: Seconds to wait before force kill

        Returns:
            True if process was stopped, False if already dead or error
        """
        handle = ProcessHandle(pid=pid, command_or_func="unknown")
        return self.stop_process(handle, force, timeout)

    def is_process_running(self, handle: ProcessHandle) -> bool:
        """
        Check if process is still running.

        Args:
            handle: ProcessHandle to check

        Returns:
            True if running, False otherwise
        """
        try:
            os.kill(handle.pid, 0)  # Signal 0 just checks existence
            return True
        except OSError:
            return False

    def get_process_status(self, handle: ProcessHandle) -> Dict[str, Any]:
        """
        Get process status information.

        Args:
            handle: ProcessHandle to check

        Returns:
            Dictionary with status information
        """
        running = self.is_process_running(handle)

        return {
            "pid": handle.pid,
            "running": running,
            "command": handle.command_or_func,
            "log_file": str(handle.log_file) if handle.log_file else None
        }