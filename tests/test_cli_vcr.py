# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

"""Integration tests for the CLI using pytest-vcr to record/replay HTTP interactions."""

import re

import pytest
from click.testing import CliRunner

from cf_job_logs.cli import cli

# Azure DevOps timestamp format: 2026-02-26T13:28:29.6495286Z
AZURE_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z")

TEST_PR_URLS = [
    pytest.param(
        "https://github.com/conda-forge/bun-feedstock/pull/10",
        id="bun-feedstock-pr10",
    ),
]


@pytest.mark.vcr
@pytest.mark.parametrize("pr_url", TEST_PR_URLS)
def test_list_jobs(pr_url: str):
    """Test list-jobs --all shows all jobs including succeeded."""
    runner = CliRunner()
    result = runner.invoke(cli, ["list-jobs", "--all", pr_url])

    assert result.exit_code == 0

    # Header is present
    assert "ID" in result.output
    assert "Result" in result.output
    assert "Platform" in result.output
    assert "Name" in result.output

    # --all shows both succeeded and failed jobs
    assert "succeeded" in result.output
    assert "failed" in result.output


@pytest.mark.vcr
@pytest.mark.parametrize("pr_url", TEST_PR_URLS)
def test_list_jobs_failed_only(pr_url: str):
    """Test list-jobs (default) shows only failed jobs."""
    runner = CliRunner()
    result = runner.invoke(cli, ["list-jobs", pr_url])

    assert result.exit_code == 0

    # Header is present
    assert "ID" in result.output
    assert "Result" in result.output
    assert "Platform" in result.output
    assert "Name" in result.output

    # Only failed jobs shown (no succeeded)
    assert "failed" in result.output
    assert "succeeded" not in result.output


@pytest.mark.vcr
@pytest.mark.parametrize("pr_url", TEST_PR_URLS)
def test_full_workflow(pr_url: str):
    """Test full workflow: list jobs, pick a failing one, download its log."""
    runner = CliRunner()

    # Step 1: List failed jobs (cf-job-logs list-jobs PR_URL)
    result = runner.invoke(cli, ["list-jobs", pr_url])
    assert result.exit_code == 0

    list_output = result.output
    lines = list_output.strip().split("\n")

    # Skip header and separator lines, find first failed job
    job_lines = [line for line in lines[2:] if line.strip()]
    assert len(job_lines) > 0, "Expected at least one failed job"

    # Parse job ID from first column (first 40 chars)
    job_id = job_lines[0].split()[0]
    assert len(job_id) > 0, "Could not parse job ID"

    # Step 2: Download the log for this job (cf-job-logs download-log PR_URL JOB_ID)
    result = runner.invoke(cli, ["download-log", pr_url, job_id])
    assert result.exit_code == 0

    log_output = result.output
    assert len(log_output) > 0, "Expected log output"
    # Sanitized logs should not have Azure timestamps
    assert not AZURE_TIMESTAMP_PATTERN.search(log_output), (
        "Sanitized log should not contain timestamps"
    )

    assert "Error: " in log_output
    assert "sha256 checksum validation failed" in log_output

    # Step 3: Download raw log with --no-sanitize
    result = runner.invoke(cli, ["download-log", "--no-sanitize", pr_url, job_id])
    assert result.exit_code == 0

    raw_output = result.output
    assert len(raw_output) > 0, "Expected raw log output"
    # Raw logs should have timestamps
    assert AZURE_TIMESTAMP_PATTERN.search(raw_output), (
        "Raw log should contain timestamps"
    )
