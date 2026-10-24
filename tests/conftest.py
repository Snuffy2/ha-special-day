"""Enable loading this repository's custom integration in Home Assistant."""

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations: None) -> None:
    """Permit real integration loading in the test instance."""
