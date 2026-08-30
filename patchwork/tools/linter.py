"""
patchwork.tools.linter
========================
Deterministic static-analysis wrapper around `ruff check` for the
Patchwork self-healing code-audit engine.

Like `sandbox.py`, this module knows nothing about the SLM, LangGraph, or
Ollama -- it takes source code as a string, runs `ruff` against it in
isolation, and returns strictly-typed, truncated diagnostics that are
safe to inject into a constrained-context prompt.

Design goals (see `critical_engineering_and_execution_advice` and
`PATCHWORK_ARCHITECTURE__EDGE_CASE___FAILURE_MODE_CHECKLIST`):
    * Ruff's own JSON output is the source of truth -- this module parses
      it defensively rather than assuming any log format is stable across
      ruff versions.
    * A `ruff` binary that is missing, a malformed JSON response, or a
      subprocess that stalls are all infrastructure failures distinct
      from "the code has lint issues" -- they are surfaced separately via
      `LintRunResult.error_message` / `success` rather than raised.
    * Output is truncated before re-entering the LLM context window, for
      the same VRAM/KV-cache reasons as the sandbox tool.
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

# --- Tunables ---------------------------------------------------------

DEFAULT_TIMEOUT_SEC: Final[int] = 10
MAX_ISSUES_RETAINED: Final[int] = 30
MAX_MESSAGE_CHARS: Final[int] = 300


class LintIssue(BaseModel):
    """A single diagnostic reported by Ruff for one source file.

    Attributes:
        code: Ruff's rule code, e.g. `"F401"`, `"B006"`. `None` for the
            rare diagnostic ruff emits without a rule code attached.
        name: Ruff's human-readable rule name, e.g. `"unused-import"`.
        message: Short description of the specific violation.
        line: 1-indexed line number where the issue starts.
        column: 1-indexed column number where the issue starts.
        severity: Ruff's own severity classification for the rule.
        is_fixable: True if ruff reports an automatic fix is available
            for this issue (safe or unsafe).
    """

    code: str | None = None
    name: str | None = None
    message: str
    line: int
    column: int
    severity: str = "error"
    is_fixable: bool = False


class LintRunResult(BaseModel):
    """Strictly-typed result of a single `ruff check` invocation.

    Attributes:
        success: True if ruff *executed* without an infrastructure
            failure. Note this is independent of whether issues were
            found -- a file with 20 lint issues is still `success=True`.
        issues: Parsed, truncated list of individual diagnostics.
        issue_count_total: The true number of issues ruff reported,
            before truncation. Compare against `len(issues)` to know if
            truncation occurred.
        timed_out: True if the ruff subprocess exceeded `timeout_sec`.
        duration_sec: Wall-clock time the subprocess actually ran for.
        error_message: Populated only for infrastructure-level failures
            (ruff missing, unparseable JSON, timeout) -- never for normal
            lint findings, which live in `issues` instead.
    """

    success: bool
    issues: list[LintIssue] = Field(default_factory=list)
    issue_count_total: int = 0
    timed_out: bool = False
    duration_sec: float = Field(ge=0.0)
    error_message: str | None = None


def _truncate_message(message: str, max_chars: int = MAX_MESSAGE_CHARS) -> str:
    """Truncates a single diagnostic message to a maximum character count.

    Args:
        message: Raw message text from ruff.
        max_chars: Maximum characters to retain.

    Returns:
        The message, unchanged if short enough, otherwise cut to
        `max_chars` with a truncation marker appended.
    """
    if len(message) <= max_chars:
        return message
    return f"{message[:max_chars]}...[truncated]"


def _parse_ruff_json(raw_stdout: str) -> list[LintIssue]:
    """Parses ruff's `--output-format=json` stdout into `LintIssue`s.

    Args:
        raw_stdout: Raw stdout captured from the `ruff check` subprocess.

    Returns:
        A list of parsed issues. Entries that don't match the expected
        shape are skipped individually rather than failing the whole
        parse, since a single malformed entry should not hide every
        other real diagnostic from the reflection loop.

    Raises:
        json.JSONDecodeError: If `raw_stdout` is not valid JSON at all.
    """
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
) -> LintRunResult:
    """Runs `ruff check` against a string of Python source code.

    Args:
        source_code: The full contents of the module to lint.
        timeout_sec: Hard wall-clock limit, in seconds, for the ruff
            subprocess. Must be strictly positive.

    Returns:
        A `LintRunResult`. Ruff exiting non-zero because it *found*
        issues is a normal, expected outcome and is represented via a
        populated `issues` list with `success=True` -- it is not treated
        as an error. Only infrastructure failures set `success=False`.

    Raises:
        ValueError: If `timeout_sec` is not a positive number.
    """
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
                [sys.executable, "-m", "ruff", "check", "--output-format=json", str(target_path)],
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