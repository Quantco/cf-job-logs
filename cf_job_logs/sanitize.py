# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import re

# Match and strip an ISO-8601-style timestamp prefix (with optional leading whitespace)
TIMESTAMP_PREFIX_PATTERN = re.compile(
    r"^(\s*\d{4}-\d{2}-\d{2}T"
    r"\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})\s+)"
)


def sanitize_log_text(log_text: str) -> str:
    """Remove timestamps from each line of the log text and filter out verbose
    build output.

    Args:
        log_text: The original log text.
    Returns:
        The log text with timestamps removed and verbose lines filtered out.
    """

    # Skip to relevant build output if possible
    if "rattler-build build" in log_text:
        start_log_idx = log_text.index("rattler-build build")
        log_text = log_text[start_log_idx:]
    elif "conda-build /home/conda/recipe_root" in log_text:
        start_log_idx = log_text.index("conda-build /home/conda/recipe_root")
        log_text = log_text[start_log_idx:]

    lines = log_text.splitlines()
    cleaned_lines = []

    for line in lines:
        # Remove timestamp prefixes when present, otherwise keep the line unchanged
        match = TIMESTAMP_PREFIX_PATTERN.match(line)
        if match:
            cleaned = line[match.end() :]
        else:
            cleaned = line

        # Filter out "copying ... -> ..." and "creating <path>" lines from build output
        # These are setuptools/distutils verbose output lines that add noise
        if re.match(r"^(?:│\s*│\s*)?copying\s+\S+\s+->\s+\S+", cleaned):
            continue
        if re.match(r"^(?:│\s*│\s*)?creating\s+\S+", cleaned):
            continue

        cleaned_lines.append(cleaned)

    return "\n".join(cleaned_lines)
