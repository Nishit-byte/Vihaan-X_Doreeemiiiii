"""Pytest configuration and custom marker definitions for M2 tests."""

import os
from pathlib import Path
import pytest

# Best-effort dotenv load so markers have access to GEMINI_API_KEY
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except Exception:
    pass


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "network: marks tests that require external network access (skipped unless M2_NETWORK_TESTS=1)",
    )
    config.addinivalue_line(
        "markers",
        "gemini: marks tests that require live Gemini API access (skipped unless GEMINI_API_KEY is set)",
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    # Check for network marker
    for _ in item.iter_markers(name="network"):
        if os.getenv("M2_NETWORK_TESTS") != "1":
            pytest.skip("Skipped: requires M2_NETWORK_TESTS=1")

    # Check for gemini marker
    for _ in item.iter_markers(name="gemini"):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            pytest.skip("Skipped: requires GEMINI_API_KEY")
