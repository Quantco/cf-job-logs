# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_httpx_async_client() -> Callable[[str, str, Exception | None], AsyncMock]:
    """Fixture that returns a setup function for mocking httpx.AsyncClient.

    Returns:
        A callable that takes:
            - text_data (str): Text data for the mocked response
            - expected_url (str): Expected URL that should be called
            - raise_for_status_side_effect (Exception | None): Optional exception to raise
        And returns an AsyncMock instance of the httpx.AsyncClient.
    """

    def _setup(
        text_data: str,
        expected_url: str,
        raise_for_status_side_effect: Exception | None = None,
    ) -> AsyncMock:
        mock_response = MagicMock()
        mock_response.url = expected_url
        mock_response.text = text_data
        if raise_for_status_side_effect is not None:
            mock_response.raise_for_status.side_effect = raise_for_status_side_effect

        async def mock_get(request_url: str, **kwargs: object) -> MagicMock:
            assert request_url == expected_url, (
                f"Expected URL {expected_url}, got {request_url}"
            )
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get)

        return mock_client

    return _setup
