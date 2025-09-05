#!/usr/bin/env python3
"""
Installation verification script for pctl
Checks all prerequisites and provides installation guidance
"""

import subprocess
import sys
import shutil
from pathlib import Path

def check_command(cmd: str, name: str = None) -> bool:
    """Check if a command exists in PATH"""
    name = name or cmd
    if shutil.which(cmd):
        print(f"✅ {name} found")
        return True
    else:
        print(f"❌ {name} not found")
        return False

def check_python_version() -> bool:
    """Check Python version"""
    version = sys.version_info
    if version >= (3, 13):
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} (required: 3.13+)")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} (required: 3.13+)")
        return False

def check_docker_running() -> bool:
    """Check if Docker daemon is running"""
    try:
        result = subprocess.run(['docker', 'ps'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Docker daemon is running")
            return True
        else:
            print("❌ Docker daemon not running")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Docker not accessible")
        return False

def check_frodo_version() -> bool:
    """Check Frodo CLI version"""
    try:
        result = subprocess.run(['frodo', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ Frodo CLI {version}")
            return True
        else:
            print("❌ Frodo CLI not working")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Frodo CLI not found")
        return False

def check_pctl_installation() -> bool:
    """Check pctl installation (both global and local)"""
    if not shutil.which('uv'):
        print("❌ UV not found")
        return False
    
    print("✅ UV found")
    
    # Check for global installation first
    if shutil.which('pctl'):
        try:
            result = subprocess.run(['pctl', '--help'], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and 'pctl' in result.stdout:
                print("✅ pctl globally installed and working")
                return True
        except subprocess.TimeoutExpired:
            print("❌ pctl global installation check timed out")
    
    # Check if we're in a pctl project for development mode
    if Path('pyproject.toml').exists():
        try:
            result = subprocess.run(['uv', 'run', 'pctl', '--help'], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and 'pctl' in result.stdout:
                print("✅ pctl development mode working (use 'uv run pctl')")
                return True
            else:
                print("❌ pctl not installed or not working")
                print("   For global install: uv tool install .")
                print("   For development: uv sync")
                return False
        except subprocess.TimeoutExpired:
            print("❌ pctl installation check timed out")
            return False
    else:
        print("❌ pctl not found globally and not in project directory")
        print("   Install with: uv tool install <path-to-pctl>")
        return False

def main():
    print("🔍 Verifying pctl installation prerequisites...\n")
    
    checks = [
        ("Python 3.13+", check_python_version),
        ("UV Package Manager", lambda: check_command('uv')),
        ("Docker", lambda: check_command('docker')),
        ("Docker Compose", lambda: check_command('docker-compose')),
        ("Docker Running", check_docker_running),
        ("curl", lambda: check_command('curl')),
        ("Frodo CLI", check_frodo_version),
        ("pctl Installation", check_pctl_installation),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\nChecking {name}:")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error checking {name}: {e}")
            results.append((name, False))
    
    print("\n" + "="*50)
    print("📊 VERIFICATION SUMMARY")
    print("="*50)
    
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 All checks passed! You're ready to use pctl.")
        print("\nQuick start:")
        if shutil.which('pctl'):
            print("  pctl --help")
            print("  pctl elk health")
        else:
            print("  uv run pctl --help")
            print("  uv run pctl elk health")
    else:
        print(f"\n⚠️  {failed} issues found. Please install missing dependencies.")
        print("\nSee README.md for installation requirements.")
        
        sys.exit(1)

if __name__ == "__main__":
    main()