# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import pytest

from cf_job_logs.sanitize import sanitize_log_text


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


def test_sanitize_log_text_preserves_non_timestamp_prefixes():
    """Non-timestamp lines should keep their leading token and spacing."""
    log_text = "ERROR: Build failed\n  leading spaces stay here"

    assert sanitize_log_text(log_text) == log_text


@pytest.mark.parametrize(
    "log_file",
    [
        "tests/data/long_log_conda_build.txt",
        "tests/data/long_log_rattler_build.txt",
    ],
)
def test_sanitize_logs_shorten_long_files(log_file):
    """Test that sanitize_log_text correctly shortens long log files."""
    with open(log_file, encoding="utf-8") as f:
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
