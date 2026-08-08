import os

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires local Postgres or MinIO services",
    )


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_INTEGRATION_TESTS") == "1":
        return

    skip_integration = pytest.mark.skip(
        reason="set RUN_INTEGRATION_TESTS=1 to run integration tests"
    )

    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
