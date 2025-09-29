"""
Version utilities - Read version from package metadata
"""

from importlib.metadata import version


def get_version() -> str:
    """
    Get version from package metadata

    Returns:
        Version string or fallback if not found
    """
    try:
        return version('pctl')
    except Exception:
        return "unknown"