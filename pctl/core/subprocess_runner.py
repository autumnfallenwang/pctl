"""
Async subprocess runner for external CLI tools (common utility)
"""

import asyncio
from pathlib import Path
from typing import Optional, List
from loguru import logger

from .exceptions import ServiceError


class CommandResult:
    """Result of subprocess command execution"""
    
    def __init__(self, stdout: str, stderr: str, returncode: int):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = returncode == 0
    
    @classmethod
    def from_process(cls, stdout: bytes, stderr: bytes, returncode: int) -> 'CommandResult':
        """Create from subprocess result"""
        return cls(
            stdout.decode('utf-8', errors='replace'),
            stderr.decode('utf-8', errors='replace'), 
            returncode
        )


class SubprocessRunner:
    """Async subprocess execution for external CLI tools"""
    
    def __init__(self):
        self.logger = logger
    
    async def run_command(self, 
                         cmd: List[str], 
                         cwd: Optional[Path] = None,
                         timeout: int = 300) -> CommandResult:
        """Run command with timeout and proper error handling"""
        
        try:
            self.logger.debug(f"Running command: {' '.join(cmd)}")
            if cwd:
                self.logger.debug(f"Working directory: {cwd}")
            
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
                raise ServiceError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
            
            result = CommandResult.from_process(stdout, stderr, process.returncode)
            
            if not result.success:
                self.logger.error(f"Command failed: {' '.join(cmd)}")
                self.logger.error(f"Exit code: {result.returncode}")
                self.logger.error(f"stderr: {result.stderr}")
            
            return result
            
        except FileNotFoundError:
            raise ServiceError(f"Command not found: {cmd[0]}")
        except Exception as e:
            raise ServiceError(f"Failed to execute command {' '.join(cmd)}: {e}")
    
    def start_background_process(self, 
                                cmd: List[str], 
                                log_file: Path,
                                pid_file: Path,
                                cwd: Optional[Path] = None) -> int:
        """Start background process and return PID (synchronous) - legacy method with PID file"""
        
        import subprocess
        import os
        
        try:
            # Start process in background
            process = subprocess.Popen(
                cmd,
                stdout=open(log_file, 'a'),
                stderr=subprocess.STDOUT, 
                cwd=cwd,
                preexec_fn=os.setsid  # Create new process group
            )
            
            # Write PID file
            with open(pid_file, 'w') as f:
                f.write(str(process.pid))
            
            self.logger.info(f"Started background process PID {process.pid}")
            return process.pid
            
        except Exception as e:
            raise ServiceError(f"Failed to start background process: {e}")
    
    def start_background_process_simple(self, 
                                       cmd: List[str], 
                                       log_file: Path,
                                       cwd: Optional[Path] = None) -> int:
        """Start background process and return PID (no PID file needed)"""
        
        import subprocess
        import os
        
        try:
            # Start process in background
            process = subprocess.Popen(
                cmd,
                stdout=open(log_file, 'a'),
                stderr=subprocess.STDOUT, 
                cwd=cwd,
                preexec_fn=os.setsid  # Create new process group
            )
            
            self.logger.info(f"Started background process PID {process.pid}")
            return process.pid
            
        except Exception as e:
            raise ServiceError(f"Failed to start background process: {e}")
    
    def stop_process_by_pid(self, pid: int) -> bool:
        """Stop process by PID with graceful shutdown"""
        
        import os
        import signal
        import time
        
        try:
            # Check if process exists
            os.kill(pid, 0)
        except OSError:
            self.logger.warning(f"Process {pid} not running")
            return False
        
        try:
            # Try graceful shutdown first
            os.kill(pid, signal.SIGTERM)
            
            # Wait for process to stop
            for i in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(1)
                except OSError:
                    self.logger.info(f"Process {pid} stopped gracefully")
                    return True
            
            # Force kill if still running
            self.logger.warning(f"Force killing process {pid}")
            os.kill(pid, signal.SIGKILL)
            return True
            
        except OSError as e:
            self.logger.error(f"Failed to stop process {pid}: {e}")
            return False