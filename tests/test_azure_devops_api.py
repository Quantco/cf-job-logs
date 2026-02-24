# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import patch

import httpx
import pytest

from cf_job_logs.azure_devops_api import (
    BuildLogsUnavailableError,
    FailedStepWithPlatform,
    fetch_all_logs_async,
    fetch_azure_steps,
    fetch_log_async,
    get_failed_steps_with_platform,
    sanitize_log_text,
)
from cf_job_logs.models import LogInfo, TimelineRecord


def test_get_failed_steps_with_platform():
    """Test get_failed_steps_with_platform function."""
    # Create mock timeline records
    parent_job = TimelineRecord(
        id="parent_id",
        parentId=None,
        type="Job",
        name="parent-job: Linux-64",
        result="failed",
        log=None,
    )

    child_task1 = TimelineRecord(
        id="child-id-1",
        parentId="parent_id",
        type="Task",
        name="child-task-1: Build",
        result="failed",
        log=LogInfo(url="https://example.com/log"),
    )

    child_task2 = TimelineRecord(
        id="child-id-2",
        parentId="parent_id",
        type="Task",
        name="child-task-2: Build",
        result="succeeded",
        log=None,
    )

    all_records = [parent_job, child_task1, child_task2]

    result = get_failed_steps_with_platform(all_records)

    assert len(result) == 1

    assert result[0].task_name == "child-task-1: Build"
    assert result[0].platform == "parent-job: Linux-64"
    assert result[0].record.id == "child-id-1"


def test_get_failed_steps_with_platform_handles_missing_parent():
    """Test get_failed_steps_with_platform handles records without parent_id."""
    task_without_parent = TimelineRecord(
        id="task-1",
        parentId=None,
        type="Task",
        name="Build",
        result="failed",
        log=LogInfo(url="https://example.com/log"),
    )

    all_records = [task_without_parent]

    result = get_failed_steps_with_platform(all_records)

    assert len(result) == 1
    assert result[0].platform == "Unknown Platform"


def test_sanitize_log_text():
    """Test sanitize_log_text removes timestamps from log lines."""
    # Test empty log
    assert sanitize_log_text("") == ""

    # Test single line
    assert (
        sanitize_log_text("2025-11-17T23:07:21.9988730Z ERROR: Build failed")
        == "ERROR: Build failed"
    )

    # Test multiple lines
    log_with_timestamps = """
2025-11-17T23:07:21.9988730Z ##[section]Starting: Initialize job
2025-11-17T23:07:21.9992346Z Agent name: 'Azure Pipelines 8'
2025-11-17T23:07:21.9992889Z Agent machine name: 'runnervmr8kkp'"""

    result = sanitize_log_text(log_with_timestamps)
    expected = """
##[section]Starting: Initialize job
Agent name: 'Azure Pipelines 8'
Agent machine name: 'runnervmr8kkp'"""
    assert result == expected


@pytest.mark.parametrize(
    "log_file",
    [
        "tests/data/long_log_conda_build.txt",
        "tests/data/long_log_rattler_build.txt",
    ],
)
def test_sanitize_logs_shorten_long_files(log_file):
    """Test that sanitize_log_text correctly shortens long log files."""
    with open(log_file) as f:
        original_logs = f.read()

    sanitized_logs = sanitize_log_text(original_logs)

    assert (
        "creating build/lib.linux-aarch64-cpython-310/onnx/backend/test/data/node/test_less_uint16/test_data_set_0"
        not in sanitized_logs
    )
    assert (
        "copying onnx/backend/test/data/node/test_less_uint16/test_data_set_0/input_0.pb -> build/lib.linux-aarch64-cpython-310/onnx/backend/test/data/node/test_less_uint16/test_data_set_0"
        not in sanitized_logs
    )

    assert len(sanitized_logs) < 0.5 * len(original_logs)


def test_fetch_azure_steps(mock_httpx_client):
    """Test fetch_azure_steps returns timeline records from Azure DevOps API."""
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


@pytest.mark.asyncio
async def test_fetch_log_async(mock_httpx_async_client):
    """Test fetch_log_async returns log content with timestamps removed."""
    expected_url = (
        "https://dev.azure.com/conda-forge/project/_apis/build/builds/123/logs/1"
    )
    log_text = "2025-11-17T23:07:21.9988730Z ERROR: Build failed\n2025-11-17T23:07:22.0000000Z INFO: Done"

    mock_client = mock_httpx_async_client(
        text_data=log_text,
        expected_url=expected_url,
    )

    result = await fetch_log_async(mock_client, expected_url)

    assert result == "ERROR: Build failed\nINFO: Done"
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
@patch("cf_job_logs.azure_devops_api.fetch_log_async")
async def test_fetch_all_logs(mock_fetch_log_async):
    """Test fetch_all_logs returns failed steps paired with their log content."""
    step1 = FailedStepWithPlatform(
        task_name="Build",
        platform="linux-64",
        record=TimelineRecord(
            id="task-1",
            parentId="job-1",
            type="Task",
            name="Build",
            result="failed",
            log=LogInfo(url="https://example.com/log1"),
        ),
    )

    step2 = FailedStepWithPlatform(
        task_name="Test",
        platform="win-64",
        record=TimelineRecord(
            id="task-2",
            parentId="job-2",
            type="Task",
            name="Test",
            result="failed",
            log=LogInfo(url="https://example.com/log2"),
        ),
    )

    failed_steps = [step1, step2]
    mock_fetch_log_async.side_effect = [
        "ERROR: Build failed",
        "WARNING: Test failed",
    ]

    result = await fetch_all_logs_async(failed_steps)

    assert len(result) == 2
    assert result[0].step.task_name == "Build"
    assert result[0].sanitized_log_content == "ERROR: Build failed"
    assert result[1].step.task_name == "Test"
    assert result[1].sanitized_log_content == "WARNING: Test failed"


@patch("cf_job_logs.azure_devops_api.fetch_log_async")
@pytest.mark.asyncio
async def test_fetch_all_logs_handles_exceptions(mock_fetch_log_async):
    """Test fetch_all_logs raises exception when log fetching fails."""
    step1 = FailedStepWithPlatform(
        task_name="Build",
        platform="linux-64",
        record=TimelineRecord(
            id="task-1",
            parentId="job-1",
            type="Task",
            name="Build",
            result="failed",
            log=LogInfo(url="https://example.com/log1"),
        ),
    )

    failed_steps = [step1]
    mock_fetch_log_async.side_effect = httpx.HTTPError("Connection error")

    with pytest.raises(httpx.HTTPError, match="Connection error"):
        await fetch_all_logs_async(failed_steps)


def test_fetch_azure_steps_handles_http_error(mock_httpx_client):
    """Test fetch_azure_steps raises RuntimeError when HTTP request fails."""
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


def test_fetch_azure_steps_raises_build_logs_unavailable_on_404(mock_httpx_client):
    """Test fetch_azure_steps raises BuildLogsUnavailableError when 404 response."""
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
