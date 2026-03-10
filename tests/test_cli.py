# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for CLI error cases that are hard to test with VCR."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from cf_job_logs.cli import cli
from cf_job_logs.models import CIResult, GitHubActionsRecord, LogInfo, TimelineRecord

SAMPLE_RECORDS = [
    TimelineRecord(
        id="job-1",
        parentId=None,
        type="Job",
        name="linux_64",
        result=CIResult.FAILED,
        log=None,
    ),
    TimelineRecord(
        id="task-1",
        parentId="job-1",
        type="Task",
        name="Run build",
        result=CIResult.FAILED,
        log=LogInfo(url="https://example.com/log/1"),
    ),
    TimelineRecord(
        id="task-without-log",
        parentId="job-1",
        type="Task",
        name="Checkout",
        result=CIResult.SUCCEEDED,
        log=None,
    ),
    GitHubActionsRecord(
        id="gha-1",
        parentId=None,
        name="linux_64_github_actions",
        result=CIResult.SKIPPED,
        log=None,
    ),
    GitHubActionsRecord(
        id="gha-2",
        parentId="gha-1",
        name="Run tests",
        result=CIResult.FAILED,
        log=LogInfo(url="https://example.com/log/2"),
    ),
]

PR_URL = "https://github.com/conda-forge/some-feedstock/pull/42"
PATCH_RECORDS = patch("cf_job_logs.cli._get_ci_records", return_value=SAMPLE_RECORDS)
PATCH_RECORDS_EMPTY = patch("cf_job_logs.cli._get_ci_records", return_value=[])


def test_list_jobs_empty():
    """Empty CI prints a message."""
    runner = CliRunner()
    with PATCH_RECORDS_EMPTY:
        result = runner.invoke(cli, ["list-jobs", PR_URL])

    assert result.exit_code == 0
    assert "No tasks with logs found." in result.output


def test_download_log_unknown_job_id():
    """download-log exits with error for unknown job ID."""
    runner = CliRunner()
    with PATCH_RECORDS:
        result = runner.invoke(cli, ["download-log", PR_URL, "no-such-id"])

    assert result.exit_code == 1
    assert "No job found with ID 'no-such-id'" in result.output


def test_download_log_job_without_log():
    """download-log exits with error when job has no log."""
    runner = CliRunner()
    with PATCH_RECORDS:
        result = runner.invoke(cli, ["download-log", PR_URL, "task-without-log"])

    assert result.exit_code == 1
    assert "has no log" in result.output


def test_list_jobs_json_format():
    """list-jobs with --json outputs proper JSON."""
    runner = CliRunner()
    with PATCH_RECORDS:
        result = runner.invoke(cli, ["list-jobs", PR_URL, "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0] == {
        "id": "task-1",
        "result": "failed",
        "platform": "linux_64",
        "name": "Run build",
    }
    assert data[1] == {
        "id": "gha-2",
        "result": "failed",
        "platform": "linux_64_github_actions",
        "name": "Run tests",
    }


def test_list_jobs_json_empty():
    """list-jobs with --json outputs empty array when no tasks found."""
    runner = CliRunner()
    with PATCH_RECORDS_EMPTY:
        result = runner.invoke(cli, ["list-jobs", PR_URL, "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


def test_list_jobs_json_all_flag():
    """list-jobs with --json and --all includes all tasks."""
    records = SAMPLE_RECORDS + [
        TimelineRecord(
            id="task-2",
            parentId="job-1",
            type="Task",
            name="Test",
            result=CIResult.SUCCEEDED,
            log=LogInfo(url="https://example.com/log/2"),
        ),
    ]
    with patch("cf_job_logs.cli._get_ci_records", return_value=records):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-jobs", PR_URL, "--json", "--all"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 3
    assert data[0]["id"] == "task-1"
    assert data[1]["id"] == "gha-2"
    assert data[2]["id"] == "task-2"


def test_no_command_exits():
    """Running without a subcommand shows help."""
    runner = CliRunner()
    result = runner.invoke(cli, [])

    # Click shows help by default when no command is given (exit code 0)
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Commands:" in result.output
