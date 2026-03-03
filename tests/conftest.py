# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

# ruff: noqa: F401 (unused imports are needed to register fixtures)

from pathlib import Path

import pytest

from tests.fixtures.mock_httpx_async_client import mock_httpx_async_client
from tests.fixtures.mock_httpx_client import mock_httpx_client

CASSETTE_DIR = Path(__file__).parent / "cassettes"


def _scrub_request_headers(request):
    """Remove all request headers."""
    request.headers = {}
    return request


def _scrub_response_headers(response):
    """Remove all response headers."""
    response["headers"] = {}
    return response


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "record_mode": "once",
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "before_record_request": _scrub_request_headers,
        "before_record_response": _scrub_response_headers,
        "decode_compressed_response": True,
    }
