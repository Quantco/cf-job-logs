# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

# ruff: noqa: F401 (unused imports are needed to register fixtures)

from pathlib import Path

import pytest

from tests.fixtures.mock_httpx_async_client import mock_httpx_async_client
from tests.fixtures.mock_httpx_client import mock_httpx_client

CASSETTE_DIR = Path(__file__).parent / "cassettes"


FILTERED_HEADERS = [
    "authorization",
    "Authorization",
    "X-TFS-Session",
    "X-TFS-ProcessId",
    "X-VSS-E2EID",
    "X-VSS-SenderDeploymentId",
    "X-GitHub-Api-Version",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-used",
    "x-ratelimit-resource",
    "x-github-request-id",
    "x-github-media-type",
    "x-oauth-scopes",
    "x-accepted-oauth-scopes",
    "cookie",
    "set-cookie",
]


def _scrub_response_headers(response):
    """Remove sensitive headers from response."""
    headers_to_remove = [
        h
        for h in response["headers"]
        if h.lower() in [f.lower() for f in FILTERED_HEADERS]
    ]
    for header in headers_to_remove:
        del response["headers"][header]
    return response


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "filter_headers": FILTERED_HEADERS,
        "record_mode": "once",
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "before_record_response": _scrub_response_headers,
        "decode_compressed_response": True,
    }
