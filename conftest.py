"""
Global pytest configuration for pctl
"""

import pytest

def pytest_addoption(parser):
    """Add integration test option to pytest"""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests"
    )

def pytest_configure(config):
    """Configure pytest for integration tests"""
    config.addinivalue_line("markers", "integration: mark test as integration test")

def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle integration tests"""
    if config.getoption("--integration"):
        # Only run integration tests
        skip_unit = pytest.mark.skip(reason="running integration tests only")
        for item in items:
            if "integration" not in item.keywords:
                item.add_marker(skip_unit)
    else:
        # Skip integration tests by default
        skip_integration = pytest.mark.skip(reason="use --integration to run integration tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)