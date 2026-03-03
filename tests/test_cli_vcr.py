# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

"""Integration tests for the CLI using pytest-vcr to record/replay HTTP interactions."""

import re
from unittest.mock import patch

import pytest

from cf_job_logs.cli import main

# Azure DevOps timestamp format: 2026-02-26T13:28:29.6495286Z
AZURE_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z")

TEST_PR_URLS: list[tuple[str, str]] = [
    ("bun-feedstock-pr10", "https://github.com/conda-forge/bun-feedstock/pull/10"),
]


@pytest.mark.vcr
@pytest.mark.parametrize("_name,pr_url", TEST_PR_URLS, ids=[t[0] for t in TEST_PR_URLS])
def test_list_jobs(_name: str, pr_url: str, capsys):
    """Test list-jobs --all shows all jobs including succeeded."""
    with patch("sys.argv", ["cf-job-logs", "list-jobs", "--all", pr_url]):
        main()

    output = capsys.readouterr().out

    # Header is present
    assert "ID" in output
    assert "Result" in output
    assert "Platform" in output
    assert "Name" in output

    # --all shows both succeeded and failed jobs
    assert "succeeded" in output
    assert "failed" in output


@pytest.mark.vcr
@pytest.mark.parametrize("_name,pr_url", TEST_PR_URLS, ids=[t[0] for t in TEST_PR_URLS])
def test_list_jobs_failed_only(_name: str, pr_url: str, capsys):
    """Test list-jobs (default) shows only failed jobs."""
    with patch("sys.argv", ["cf-job-logs", "list-jobs", pr_url]):
        main()

    output = capsys.readouterr().out

    # Header is present
    assert "ID" in output
    assert "Result" in output
    assert "Platform" in output
    assert "Name" in output

    # Only failed jobs shown (no succeeded)
    assert "failed" in output
    assert "succeeded" not in output


@pytest.mark.vcr
@pytest.mark.parametrize("_name,pr_url", TEST_PR_URLS, ids=[t[0] for t in TEST_PR_URLS])
def test_full_workflow(_name: str, pr_url: str, capsys):
    """Test full workflow: list jobs, pick a failing one, download its log."""
    # Step 1: List failed jobs (cf-job-logs list-jobs PR_URL)
    with patch("sys.argv", ["cf-job-logs", "list-jobs", pr_url]):
        main()

    list_output = capsys.readouterr().out
    lines = list_output.strip().split("\n")

    # Skip header and separator lines, find first failed job
    job_lines = [line for line in lines[2:] if line.strip()]
    assert len(job_lines) > 0, "Expected at least one failed job"

    # Parse job ID from first column (first 40 chars)
    job_id = job_lines[0].split()[0]
    assert len(job_id) > 0, "Could not parse job ID"

    # Step 2: Download the log for this job (cf-job-logs download-log PR_URL JOB_ID)
    with patch("sys.argv", ["cf-job-logs", "download-log", pr_url, job_id]):
        main()

    log_output = capsys.readouterr().out
    assert len(log_output) > 0, "Expected log output"
    # Sanitized logs should not have Azure timestamps
    assert not AZURE_TIMESTAMP_PATTERN.search(log_output), (
        "Sanitized log should not contain timestamps"
    )

    assert "Error: " in log_output
    assert "sha256 checksum validation failed" in log_output

    # Step 3: Download raw log with --no-sanitize
    with patch(
        "sys.argv", ["cf-job-logs", "download-log", "--no-sanitize", pr_url, job_id]
    ):
        main()

    raw_output = capsys.readouterr().out
    assert len(raw_output) > 0, "Expected raw log output"
    # Raw logs should have timestamps
    assert AZURE_TIMESTAMP_PATTERN.search(raw_output), (
        "Raw log should contain timestamps"
    )
