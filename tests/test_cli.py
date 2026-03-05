# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for CLI error cases that are hard to test with VCR."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cf_job_logs.cli import cli
from cf_job_logs.models import LogInfo, TimelineRecord

SAMPLE_RECORDS = [
    TimelineRecord(
        id="job-1",
        parentId=None,
        type="Job",
        name="linux_64",
        result="failed",
        log=None,
    ),
    TimelineRecord(
        id="task-1",
        parentId="job-1",
        type="Task",
        name="Run build",
        result="failed",
        log=LogInfo(url="https://example.com/log/1"),
    ),
    TimelineRecord(
        id="task-without-log",
        parentId="job-1",
        type="Task",
        name="Checkout",
        result="succeeded",
        log=None,
    ),
]

PR_URL = "https://github.com/conda-forge/some-feedstock/pull/42"
PATCH_RECORDS = patch(
    "cf_job_logs.cli._get_timeline_records", return_value=SAMPLE_RECORDS
)
PATCH_RECORDS_EMPTY = patch("cf_job_logs.cli._get_timeline_records", return_value=[])


def test_list_jobs_empty():
    """Empty timeline prints a message."""
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


def test_no_command_exits():
    """Running without a subcommand exits with error."""
    runner = CliRunner()
    result = runner.invoke(cli, [])

    assert result.exit_code != 0
