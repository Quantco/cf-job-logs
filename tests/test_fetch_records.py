# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


from unittest.mock import patch

import httpx
import pytest

from cf_job_logs.fetch_records import (
    FailedStepWithPlatform,
    _fetch_log_async,
    fetch_all_logs_async,
    get_failed_steps_with_platform,
)
from cf_job_logs.models import (
    LogInfo,
    TimelineRecord,
)


@pytest.mark.asyncio
@patch("cf_job_logs.fetch_records._fetch_log_async")
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


@patch("cf_job_logs.fetch_records._fetch_log_async")
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


def test_get_failed_steps_with_platform():
    """Test get_failed_steps_with_platform extracts failed tasks with platform."""
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

    all_records: list[TimelineRecord] = [parent_job, child_task1, child_task2]

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

    all_records: list[TimelineRecord] = [task_without_parent]

    result = get_failed_steps_with_platform(all_records)

    assert len(result) == 1
    assert result[0].platform == "Unknown Platform"


@pytest.mark.asyncio
async def test_fetch_log_async_azure(mock_httpx_async_client):
    """Test _fetch_log_async returns sanitized log content for Azure records."""
    expected_url = (
        "https://dev.azure.com/conda-forge/project/_apis/build/builds/123/logs/1"
    )
    log_text = "2025-11-17T23:07:21.9988730Z ERROR: Build failed\n2025-11-17T23:07:22.0000000Z INFO: Done"

    mock_client = mock_httpx_async_client(
        text_data=log_text,
        expected_url=expected_url,
    )
    record = TimelineRecord(
        id="task-1",
        parentId="job-1",
        type="Task",
        name="Build",
        result="failed",
        log=LogInfo(url=expected_url),
    )

    result = await _fetch_log_async(mock_client, record)

    assert result == "ERROR: Build failed\nINFO: Done"
    mock_client.get.assert_called_once()
