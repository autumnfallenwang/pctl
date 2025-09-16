"""
Version utilities - Read version from pyproject.toml
"""

import tomllib
from pathlib import Path


def get_version() -> str:
    """
    Get version from pyproject.toml file

    Returns:
        Version string or fallback if not found
    """
    try:
        # Path from this file: pctl/core/version.py -> ../../pyproject.toml
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"

        with open(pyproject_path, 'rb') as f:
            data = tomllib.load(f)
            return data.get('project', {}).get('version', 'unknown')

    except Exception:
        # Fallback for any errors
        return "unknown"