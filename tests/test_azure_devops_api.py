# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import httpx
import pytest

from cf_job_logs.azure_devops_api import BuildLogsUnavailableError, fetch_azure_steps


def test_fetch_azure_records(mock_httpx_client):
    """Test fetch_azure_records returns azure records from Azure DevOps API."""
    project_id = "test-project-id"
    build_id = "12345"

    expected_url = f"https://dev.azure.com/conda-forge/{project_id}/_apis/build/builds/{build_id}/timeline?api-version=7.1"
    mock_client = mock_httpx_client(
        json_data={
            "records": [
                {
                    "id": "record-1",
                    "parentId": None,
                    "type": "Job",
                    "name": "linux-64",
                    "result": "succeeded",
                    "log": None,
                },
                {
                    "id": "record-2",
                    "parentId": "record-1",
                    "type": "Task",
                    "name": "Build",
                    "result": "failed",
                    "log": {"url": "https://example.com/log"},
                },
            ]
        },
        expected_url=expected_url,
    )

    result = fetch_azure_steps(mock_client, project_id, build_id)

    assert len(result) == 2
    assert result[0].id == "record-1"
    assert result[1].id == "record-2"
    mock_client.get.assert_called_once()


def test_fetch_azure_records_handles_http_error(mock_httpx_client):
    """Test fetch_azure_records raises RuntimeError when HTTP request fails."""
    project_id = "test-project-id"
    build_id = "12345"

    expected_url = f"https://dev.azure.com/conda-forge/{project_id}/_apis/build/builds/{build_id}/timeline?api-version=7.1"
    mock_client = mock_httpx_client(
        json_data={"records": []},
        expected_url=expected_url,
        raise_for_status_side_effect=httpx.HTTPError("Connection error"),
    )

    with pytest.raises(RuntimeError):
        fetch_azure_steps(mock_client, project_id, build_id)
    mock_client.get.assert_called_once()


def test_fetch_azure_records_raises_build_logs_unavailable_on_404(mock_httpx_client):
    """Test fetch_azure_records raises BuildLogsUnavailableError on 404."""
    project_id = "test-project-id"
    build_id = "12345"

    expected_url = f"https://dev.azure.com/conda-forge/{project_id}/_apis/build/builds/{build_id}/timeline?api-version=7.1"

    # Create a proper HTTPStatusError for 404
    mock_response = httpx.Response(404, request=httpx.Request("GET", expected_url))
    http_status_error = httpx.HTTPStatusError(
        "Not Found", request=mock_response.request, response=mock_response
    )

    mock_client = mock_httpx_client(
        json_data={"records": []},
        expected_url=expected_url,
        raise_for_status_side_effect=http_status_error,
    )

    with pytest.raises(BuildLogsUnavailableError):
        fetch_azure_steps(mock_client, project_id, build_id)

    mock_client.get.assert_called_once()
