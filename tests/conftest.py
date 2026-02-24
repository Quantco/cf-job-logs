# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

# ruff: noqa: F401 (unused imports are needed to register fixtures)

import os

import pytest

from tests.fixtures.mock_httpx_async_client import mock_httpx_async_client
from tests.fixtures.mock_httpx_client import mock_httpx_client


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": ["authorization", "cookie"],
        "record_mode": "none",
        "match_on": ["method", "scheme", "host", "port", "path"],
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir():
    return os.path.join(os.path.dirname(__file__), "cassettes")
