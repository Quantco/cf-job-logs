# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from cf_job_logs.github_api import PRInfo, fetch_github_check_runs
from cf_job_logs.models import CheckRun

logger = logging.getLogger(__name__)

_PASSING_CONCLUSIONS = {"success", "neutral", "skipped"}


@dataclass
class WaitResult:
    check_runs: list[CheckRun]
    timed_out: bool

    @property
    def all_passed(self) -> bool:
        return not self.timed_out and all(
            cr.conclusion in _PASSING_CONCLUSIONS for cr in self.check_runs
        )


def wait_for_check_runs(
    http_client: httpx.Client,
    pr_info: PRInfo,
    head_sha: str,
    interval: float = 10.0,
    timeout: float | None = None,
    on_status_change: Callable[[list[CheckRun]], None] | None = None,
) -> WaitResult:
    """Poll GitHub check runs until all relevant ones complete or timeout."""
    start = time.monotonic()
    consecutive_errors = 0
    max_consecutive_errors = 5
    prev_status_key: str | None = None

    while True:
        try:
            raw_runs = fetch_github_check_runs(http_client, pr_info, head_sha)
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            logger.warning(
                "Error fetching check runs (%d/%d)",
                consecutive_errors,
                max_consecutive_errors,
            )
            if consecutive_errors >= max_consecutive_errors:
                raise
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return WaitResult(check_runs=[], timed_out=True)
            time.sleep(interval)
            continue

        ci_check_runs = [cr for cr in raw_runs if cr.ci_provider is not None]

        status_key = "|".join(
            f"{s.name}:{s.status}:{s.conclusion}"
            for s in sorted(ci_check_runs, key=lambda s: s.name)
        )
        if on_status_change and status_key != prev_status_key:
            on_status_change(ci_check_runs)
        prev_status_key = status_key

        if not ci_check_runs:
            return WaitResult(check_runs=[], timed_out=False)

        if all(cr.is_completed for cr in ci_check_runs):
            return WaitResult(check_runs=ci_check_runs, timed_out=False)

        if timeout is not None and (time.monotonic() - start) >= timeout:
            return WaitResult(check_runs=ci_check_runs, timed_out=True)

        time.sleep(interval)


def format_summary_table(summaries: list[CheckRun]) -> str:
    """Format check run summaries as a human-readable table."""
    if not summaries:
        return "No relevant CI check runs found."

    id_width = max(len("ID"), max(len(str(s.id)) for s in summaries))
    name_width = max(len("Name"), max(len(s.name) for s in summaries))
    lines = [
        f"{'ID':<{id_width}}   {'Name':<{name_width}}   Result",
        "\u2500" * (id_width + name_width + 21),
    ]
    for s in summaries:
        if s.status != "completed":
            display = s.status
        elif s.conclusion == "success":
            display = "succeeded"
        else:
            display = s.conclusion or "unknown"
        lines.append(f"{s.id:<{id_width}}   {s.name:<{name_width}}   {display}")

    return "\n".join(lines)
