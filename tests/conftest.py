# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

# ruff: noqa: F401 (unused imports are needed to register fixtures)

from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pytest

from tests.fixtures.mock_httpx_async_client import mock_httpx_async_client
from tests.fixtures.mock_httpx_client import mock_httpx_client

CASSETTE_DIR = Path(__file__).parent / "cassettes"

ALLOWED_RESPONSE_HEADERS = {
    "location",  # needed for 302 replay (e.g. GitHub Actions log API → blob URL)
}

SENSITIVE_QUERY_PARAMS = {
    "sig",  # Azure Blob SAS signature; proves auth to the blob URL, so treat as secret
}


def _redact_sensitive_query_params(url: str) -> str:
    """Redact query params in SENSITIVE_QUERY_PARAMS so cassettes store no secrets."""
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query, keep_blank_values=True)

    if not any(p in query_params for p in SENSITIVE_QUERY_PARAMS):
        return url

    for p in SENSITIVE_QUERY_PARAMS:
        if p in query_params:
            query_params[p] = ["REDACTED"]
    return urlunparse(parsed_url._replace(query=urlencode(query_params, doseq=True)))


def _scrub_request(request):
    """Remove all request headers and redact sensitive query params in the URL before recording."""
    request.headers = {}
    if getattr(request, "uri", None):
        request.uri = _redact_sensitive_query_params(request.uri)
    return request


def _scrub_response(response):
    """Remove response headers except for an explicit allowlist; redact secrets in URL-valued headers."""
    headers = response.get("headers", {})

    response["headers"] = {
        k: [_redact_sensitive_query_params(v) for v in vals]
        for k, vals in headers.items()
        if k.lower() in ALLOWED_RESPONSE_HEADERS
    }
    return response


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "record_mode": "once",
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "before_record_request": _scrub_request,
        "before_record_response": _scrub_response,
        "decode_compressed_response": True,
    }
