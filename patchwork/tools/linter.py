"""
Deterministic static-analysis wrapper around `ruff check` for the Patchwork self-healing code-audit engine.
it takes source code as a string, runs `ruff` against it in isolation, and returns strictly-typed, truncated diagnostics
that are safe to inject into a constrained-context prompt.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

logger = logging.getLogger("patchwork.tools.linter")


# --- Constants

DEFAULT_TIMEOUT_SEC: Final[int] = 10
MAX_ISSUES_RETAINED: Final[int] = 30
MAX_MESSAGE_CHARS: Final[int] = 300


class LintIssue(BaseModel):  # Diagonostic about single lint violation found by ruff.
    code: str | None = (
        None  # Ruff rule code, e.g. "F401" or "B006". None if not provided.
    )
    name: str | None = (
        None  # Ruff rule name, e.g. "unused-import". None if not provided.
    )
    message: str  # Short description of the specific violation.
    line: int  # 1-indexed line number where the issue starts.
    column: int  # 1-indexed column number where the issue starts.
    severity: str = "error"  # Ruff's own severity classification for the rule.
    is_fixable: bool = False  # True if ruff reports an automatic fix is available for this issue (safe or unsafe).


class LintRunResult(BaseModel):
    success: (
        bool  # did ruff run without any failures (even if it found issues)? True/False
    )
    issues: list[LintIssue] = Field(
        default_factory=list
    )  # parsed, truncated list of individual diagnostics
    issue_count_total: int = 0  # total reported issues
    timed_out: bool = False  # True if the ruff subprocess exceeded `timeout_sec`
    duration_sec: float = Field(
        ge=0.0
    )  # wall-clock time the subprocess actually ran for
    error_message: str | None = (
        None  # failures reported for ruff (not the linting issues themselves)
    )


def _truncate_message(message: str, max_chars: int = MAX_MESSAGE_CHARS) -> str:

    if len(message) <= max_chars:
        return message
    return f"{message[:max_chars]}...[truncated]"


def _parse_ruff_json(
    raw_stdout: str,
) -> list[
    LintIssue
]:  # takes the JSON output from `ruff check --output-format=json` and returns a list of LintIssue objects, truncating messages as needed.
    raw_entries = json.loads(raw_stdout)
    issues: list[LintIssue] = []
    for entry in raw_entries:
        try:
            location = entry.get("location", {})
            fix = entry.get("fix")
            issues.append(
                LintIssue(
                    code=entry.get("code"),
                    name=entry.get("name"),
                    message=_truncate_message(entry.get("message", "")),
                    line=location.get("row", 0),
                    column=location.get("column", 0),
                    severity=entry.get("severity", "error"),
                    is_fixable=fix is not None,
                )
            )
        except (KeyError, AttributeError, TypeError) as exc:
            logger.warning(
                "lint_entry_skipped",
                extra={"event": "lint_entry_skipped", "error": str(exc)},
            )
            continue
    return issues


def run_ruff_linter(
    source_code: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> LintRunResult:  # runs `ruff check` on the provided source code string, returning a structured result with diagnostics and metadata.
    if timeout_sec <= 0:
        raise ValueError(f"timeout_sec must be positive, got {timeout_sec!r}")

    start_time = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="patchwork_lint_") as tmpdir:
        target_path = Path(tmpdir) / "target_under_lint.py"

        try:
            target_path.write_text(source_code, encoding="utf-8")
        except OSError as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                "lint_write_failed",
                extra={"event": "lint_write_failed", "error": str(exc)},
            )
            return LintRunResult(
                success=False,
                duration_sec=duration,
                error_message=f"Failed to write file for linting: {exc}",
            )

        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--output-format=json",
                    str(target_path),
                ],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,  # non-zero exit means "issues found", not a real error
            )
        except subprocess.TimeoutExpired:
            duration = time.perf_counter() - start_time
            logger.warning(
                "lint_run_timeout",
                extra={"event": "lint_run_timeout", "timeout_sec": timeout_sec},
            )
            return LintRunResult(
                success=False,
                timed_out=True,
                duration_sec=duration,
                error_message=f"Ruff execution exceeded {timeout_sec}s timeout.",
            )
        except FileNotFoundError as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                "lint_ruff_not_found",
                extra={"event": "lint_ruff_not_found", "error": str(exc)},
            )
            return LintRunResult(
                success=False,
                duration_sec=duration,
                error_message=f"ruff executable not found: {exc}",
            )

        duration = time.perf_counter() - start_time

        try:
            all_issues = _parse_ruff_json(proc.stdout)
        except json.JSONDecodeError as exc:
            logger.error(
                "lint_json_parse_failed",
                extra={"event": "lint_json_parse_failed", "error": str(exc)},
            )
            return LintRunResult(
                success=False,
                duration_sec=duration,
                error_message=f"Failed to parse ruff JSON output: {exc}",
            )

        logger.info(
            "lint_run_complete",
            extra={
                "event": "lint_run_complete",
                "issue_count": len(all_issues),
                "duration_sec": round(duration, 3),
            },
        )
        return LintRunResult(
            success=True,
            issues=all_issues[:MAX_ISSUES_RETAINED],
            issue_count_total=len(all_issues),
            duration_sec=duration,
        )
