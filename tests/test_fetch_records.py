# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


from unittest.mock import patch

import httpx
import pytest

from cf_job_logs.azure_devops_api import BuildLogsUnavailableError
from cf_job_logs.fetch_records import (
    FailedStepWithPlatform,
    _fetch_log_async,
    fetch_all_logs_async,
    fetch_ci_records,
    get_failed_steps_with_platform,
)
from cf_job_logs.github_api import NoCompletedCheckRunsError, PRInfo
from cf_job_logs.models import (
    CheckRun,
    CIProvider,
    CIRecord,
    CIResult,
    GitHubActionsRecord,
    GithubApp,
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
            result=CIResult.FAILED,
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
            result=CIResult.FAILED,
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
            result=CIResult.FAILED,
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
        result=CIResult.FAILED,
        log=None,
    )

    child_task1 = TimelineRecord(
        id="child-id-1",
        parentId="parent_id",
        type="Task",
        name="child-task-1: Build",
        result=CIResult.FAILED,
        log=LogInfo(url="https://example.com/log"),
    )

    child_task2 = TimelineRecord(
        id="child-id-2",
        parentId="parent_id",
        type="Task",
        name="child-task-2: Build",
        result=CIResult.SUCCEEDED,
        log=None,
    )

    all_records: list[CIRecord] = [parent_job, child_task1, child_task2]

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
        result=CIResult.FAILED,
        log=LogInfo(url="https://example.com/log"),
    )

    all_records: list[CIRecord] = [task_without_parent]

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
        result=CIResult.FAILED,
        log=LogInfo(url=expected_url),
    )

    result = await _fetch_log_async(mock_client, record)

    assert result == "ERROR: Build failed\nINFO: Done"
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_log_async_github_actions(mock_httpx_async_client):
    """Test _fetch_log_async returns sanitized log content for GitHub Actions records."""
    expected_url = "https://api.github.com/repos/conda-forge/example-feedstock/actions/jobs/12345/logs"
    log_text = "2025-11-17T23:07:21.9988730Z ERROR: Build failed\n2025-11-17T23:07:22.0000000Z INFO: Done"

    mock_client = mock_httpx_async_client(
        text_data=log_text,
        expected_url=expected_url,
    )

    record = GitHubActionsRecord(
        id="12345",
        parentId=None,
        type="Task",
        name="Build linux-64",
        result=CIResult.FAILED,
        log=LogInfo(url=expected_url),
    )

    with patch(
        "cf_job_logs.fetch_records.get_github_headers",
        return_value={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": "Bearer test-token",
        },
    ):
        result = await _fetch_log_async(mock_client, record)

    assert result == "ERROR: Build failed\nINFO: Done"
    mock_client.get.assert_awaited_once_with(
        expected_url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": "Bearer test-token",
        },
        follow_redirects=True,
    )


def test_fetch_ci_records_converts_github_check_runs_directly():
    """GitHub Actions check runs are converted to records without an API call."""
    check_runs = [
        CheckRun(
            id=12345,
            conclusion="failure",
            external_id=None,
            name="Build linux-64",
            html_url="https://github.com/conda-forge/feedstock/actions/runs/1/job/12345",
            app=GithubApp(slug="github-actions"),
        ),
        CheckRun(
            id=67890,
            conclusion="success",
            external_id=None,
            name="Build osx-64",
            html_url="https://github.com/conda-forge/feedstock/actions/runs/1/job/67890",
            app=GithubApp(slug="github-actions"),
        ),
    ]
    pr_info = PRInfo(owner="conda-forge", repo="example-feedstock", pr_number=1)

    with httpx.Client() as client:
        result = fetch_ci_records(client, check_runs, pr_info)

    assert len(result) == 2
    assert isinstance(result[0], GitHubActionsRecord)
    assert result[0].id == "12345"
    assert result[0].name == "Build linux-64"
    assert result[0].ci_provider == CIProvider.GITHUB_ACTIONS
    assert result[0].result == CIResult.FAILED
    assert result[0].log
    assert (
        result[0].log.url
        == "https://api.github.com/repos/conda-forge/example-feedstock/actions/jobs/12345/logs"
    )
    assert result[1].result == CIResult.SUCCEEDED


def test_fetch_ci_records_returns_only_github_when_azure_raises_no_completed_check_runs():
    """When only Azure check runs exist and get_azure_build_info raises, records are empty or GitHub-only."""
    check_runs = [
        CheckRun(
            id=1,
            conclusion="failure",
            external_id=None,
            name="Azure build",
            html_url=None,
            app=GithubApp(slug="azure-pipelines"),
        ),
    ]
    pr_info = PRInfo(owner="conda-forge", repo="example-feedstock", pr_number=1)

    with httpx.Client() as client:
        with patch(
            "cf_job_logs.fetch_records.get_azure_build_info",
            side_effect=NoCompletedCheckRunsError("No completed check runs found"),
        ):
            result = fetch_ci_records(client, check_runs, pr_info)

    assert len(result) == 0


def test_fetch_ci_records_returns_github_when_azure_logs_unavailable(caplog):
    """Azure timeline failures should not block GitHub Actions records."""
    check_runs = [
        CheckRun(
            id=1,
            conclusion="failure",
            external_id=None,
            name="Azure build",
            html_url=None,
            app=GithubApp(slug="azure-pipelines"),
        ),
        CheckRun(
            id=12345,
            conclusion="failure",
            external_id=None,
            name="Build linux-64",
            html_url="https://github.com/conda-forge/feedstock/actions/runs/1/job/12345",
            app=GithubApp(slug="github-actions"),
        ),
    ]
    pr_info = PRInfo(owner="conda-forge", repo="example-feedstock", pr_number=1)

    with httpx.Client() as client:
        with (
            patch(
                "cf_job_logs.fetch_records.get_azure_build_info",
                return_value=("build-1", "project-1"),
            ),
            patch(
                "cf_job_logs.fetch_records.fetch_azure_steps",
                side_effect=BuildLogsUnavailableError("Build logs are not available"),
            ),
        ):
            with caplog.at_level("WARNING"):
                result = fetch_ci_records(client, check_runs, pr_info)

    assert len(result) == 1
    assert isinstance(result[0], GitHubActionsRecord)
    assert result[0].id == "12345"
    assert "Azure build logs are unavailable" in caplog.text


def test_fetch_ci_records_skips_github_check_runs_without_conclusion():
    """Check runs without a conclusion are not converted to records."""
    check_runs = [
        CheckRun(
            id=12345,
            conclusion=None,
            external_id=None,
            name="Build linux-64",
            html_url=None,
            app=GithubApp(slug="github-actions"),
        ),
        CheckRun(
            id=67890,
            conclusion="failure",
            external_id=None,
            name="Build osx-64",
            html_url=None,
            app=GithubApp(slug="github-actions"),
        ),
    ]
    pr_info = PRInfo(owner="conda-forge", repo="example-feedstock", pr_number=1)

    with httpx.Client() as client:
        result = fetch_ci_records(client, check_runs, pr_info)

    assert len(result) == 1
    assert result[0].id == "67890"
    assert result[0].result == CIResult.FAILED


def test_get_failed_steps_with_platform_includes_github_records():
    """get_failed_steps_with_platform includes GitHub Actions records (platform unknown when no parent)."""
    github_record = GitHubActionsRecord(
        id="12345",
        parentId=None,
        name="Build linux-64",
        result=CIResult.FAILED,
        log=LogInfo(
            url="https://api.github.com/repos/owner/repo/actions/jobs/12345/logs"
        ),
    )
    all_records: list[CIRecord] = [github_record]

    result = get_failed_steps_with_platform(all_records)

    assert len(result) == 1
    assert result[0].task_name == "Build linux-64"
    assert result[0].platform == "Unknown Platform"
    assert result[0].record.ci_provider == CIProvider.GITHUB_ACTIONS
