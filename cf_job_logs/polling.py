# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from cf_job_logs.github_api import PRInfo, fetch_github_check_runs
from cf_job_logs.models import CheckRun, CIProvider

logger = logging.getLogger(__name__)

_KNOWN_CI_PROVIDERS = {CIProvider.AZURE, CIProvider.GITHUB_ACTIONS}
_PASSING_CONCLUSIONS = {"success", "neutral", "skipped"}


@dataclass
class CheckRunSummary:
    name: str
    status: str
    conclusion: str | None
    ci_provider: CIProvider | None = None
    html_url: str | None = None


@dataclass
class WaitResult:
    check_runs: list[CheckRunSummary]
    timed_out: bool

    @property
    def all_passed(self) -> bool:
        return not self.timed_out and all(
            cr.conclusion in _PASSING_CONCLUSIONS for cr in self.check_runs
        )


def _summarize(cr: CheckRun) -> CheckRunSummary:
    return CheckRunSummary(
        name=cr.name,
        status=cr.status,
        conclusion=cr.conclusion,
        ci_provider=cr.ci_provider,
        html_url=cr.html_url,
    )


def wait_for_check_runs(
    http_client: httpx.Client,
    pr_info: PRInfo,
    head_sha: str,
    interval: float = 10.0,
    timeout: float | None = None,
    on_status_change: Callable[[list[CheckRunSummary]], None] | None = None,
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

        relevant = [cr for cr in raw_runs if cr.ci_provider in _KNOWN_CI_PROVIDERS]
        summaries = [_summarize(cr) for cr in relevant]

        status_key = "|".join(
            f"{s.name}:{s.status}:{s.conclusion}"
            for s in sorted(summaries, key=lambda s: s.name)
        )
        if on_status_change and status_key != prev_status_key:
            on_status_change(summaries)
        prev_status_key = status_key

        if not relevant:
            return WaitResult(check_runs=[], timed_out=False)

        if all(cr.is_completed for cr in relevant):
            return WaitResult(check_runs=summaries, timed_out=False)

        if timeout is not None and (time.monotonic() - start) >= timeout:
            return WaitResult(check_runs=summaries, timed_out=True)

        time.sleep(interval)


def format_summary_table(summaries: list[CheckRunSummary]) -> str:
    """Format check run summaries as a human-readable table."""
    if not summaries:
        return "No relevant CI check runs found."

    name_width = max(len("Name"), max(len(s.name) for s in summaries))
    lines = [
        f"{'Name':<{name_width}}   Result",
        "\u2500" * (name_width + 18),
    ]
    for s in summaries:
        if s.status != "completed":
            display = s.status
        elif s.conclusion == "success":
            display = "succeeded"
        else:
            display = s.conclusion or "unknown"
        lines.append(f"{s.name:<{name_width}}   {display}")

    return "\n".join(lines)
