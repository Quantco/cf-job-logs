# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_httpx_client() -> Callable[
    [dict[str, Any], str, Exception | None, str], MagicMock
]:
    """Fixture that returns a setup function for mocking httpx.Client.

    Returns:
        A callable that takes:
            - json_data (dict[str, Any]): JSON data for the mocked response
            - expected_url (str): Expected URL that should be called
            - raise_for_status_side_effect (Exception | None): Optional exception to raise
            - request_method (str): HTTP method ('get' or 'post'), defaults to 'get'
        And returns a MagicMock instance of the httpx.Client.
    """

    def _setup(
        json_data: dict[str, Any],
        expected_url: str,
        raise_for_status_side_effect: Exception | None = None,
        request_method: str = "get",
    ) -> MagicMock:
        mock_response = MagicMock()
        mock_response.url = expected_url
        mock_response.json.return_value = json_data
        if raise_for_status_side_effect is not None:
            mock_response.raise_for_status.side_effect = raise_for_status_side_effect

        def mock_request(request_url: str, **kwargs: object) -> MagicMock:
            assert request_url == expected_url, (
                f"Expected URL {expected_url}, got {request_url}"
            )
            return mock_response

        mock_client = MagicMock()
        if request_method == "get":
            mock_client.get = MagicMock(side_effect=mock_request)
        elif request_method == "post":
            mock_client.post = MagicMock(side_effect=mock_request)

        return mock_client

    return _setup
