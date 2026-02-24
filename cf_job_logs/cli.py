# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import logging
import sys

import httpx

from cf_job_logs.azure_devops_api import (
    fetch_azure_steps,
    sanitize_log_text,
)
from cf_job_logs.github_api import (
    fetch_github_check_runs,
    fetch_pr_details,
    get_azure_build_info,
    parse_pr_url,
)
from cf_job_logs.models import TimelineRecord

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0


def _get_timeline_records(pr_url: str) -> list[TimelineRecord]:
    """Fetch Azure DevOps timeline records for a GitHub PR."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        pr_info = parse_pr_url(pr_url)
        pr_details = fetch_pr_details(client, pr_info)
        head_sha = pr_details.head.sha
        check_runs = fetch_github_check_runs(client, pr_info, head_sha)
        build_id, project_id = get_azure_build_info(check_runs)
        return fetch_azure_steps(client, project_id, build_id)


def _fetch_raw_log(log_url: str) -> str:
    """Fetch raw log content from Azure DevOps."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.get(log_url, headers={"Accept": "text/plain"})
        resp.raise_for_status()
        return resp.text


def cmd_list_jobs(args: argparse.Namespace) -> None:
    """List all jobs/tasks with logs for a PR."""
    records = _get_timeline_records(args.pr_url)

    name_by_id = {r.id: r.name for r in records}

    tasks = [r for r in records if r.log and r.type == "Task"]

    if not args.all:
        tasks = [t for t in tasks if t.result == "failed"]

    if not tasks:
        print("No tasks with logs found.")
        return

    print(f"{'ID':<40} {'Result':<12} {'Platform':<30} {'Name'}")
    print("-" * 120)

    for task in tasks:
        platform = (
            name_by_id.get(task.parent_id, "Unknown") if task.parent_id else "Unknown"
        )
        result = task.result or "pending"
        print(f"{task.id:<40} {result:<12} {platform:<30} {task.name}")


def cmd_download_log(args: argparse.Namespace) -> None:
    """Download the full (raw) log of a job."""
    records = _get_timeline_records(args.pr_url)

    record = next((r for r in records if r.id == args.job_id), None)
    if not record:
        print(f"Error: No job found with ID '{args.job_id}'", file=sys.stderr)
        sys.exit(1)

    if not record.log:
        print(f"Error: Job '{record.name}' has no log.", file=sys.stderr)
        sys.exit(1)

    log_text = _fetch_raw_log(record.log.url)
    print(log_text)


def cmd_download_sanitized_log(args: argparse.Namespace) -> None:
    """Download the sanitized log of a job."""
    records = _get_timeline_records(args.pr_url)

    record = next((r for r in records if r.id == args.job_id), None)
    if not record:
        print(f"Error: No job found with ID '{args.job_id}'", file=sys.stderr)
        sys.exit(1)

    if not record.log:
        print(f"Error: Job '{record.name}' has no log.", file=sys.stderr)
        sys.exit(1)

    log_text = _fetch_raw_log(record.log.url)
    print(sanitize_log_text(log_text))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cf-job-logs",
        description="Fetch and inspect conda-forge Azure CI logs.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # list-jobs
    list_parser = subparsers.add_parser("list-jobs", help="List all jobs for a PR.")
    list_parser.add_argument("pr_url", help="GitHub PR URL.")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="List all jobs, not just failed ones.",
    )
    list_parser.set_defaults(func=cmd_list_jobs)

    # download-log
    dl_parser = subparsers.add_parser(
        "download-log", help="Download the full log of a job."
    )
    dl_parser.add_argument("pr_url", help="GitHub PR URL.")
    dl_parser.add_argument("job_id", help="Job ID from list-jobs output.")
    dl_parser.set_defaults(func=cmd_download_log)

    # download-sanitized-log
    dl_san_parser = subparsers.add_parser(
        "download-sanitized-log",
        help="Download the sanitized log of a job.",
    )
    dl_san_parser.add_argument("pr_url", help="GitHub PR URL.")
    dl_san_parser.add_argument("job_id", help="Job ID from list-jobs output.")
    dl_san_parser.set_defaults(func=cmd_download_sanitized_log)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    args.func(args)


if __name__ == "__main__":
    main()
