"""
Deterministic, sandboxed pytest execution for the Patchwork self-healing code-audit engine.
it takes a source module and a test suite (both as strings), execute the tests in an isolated temporary
directory via `pytest`, and return a strictly-typed, truncated result.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

logger = logging.getLogger("patchwork.tools.sandbox")

# --- Constants

DEFAULT_TIMEOUT_SEC: Final[int] = 10
MAX_OUTPUT_CHARS: Final[int] = 1000
MAX_OUTPUT_LINES: Final[int] = 20
MAX_MEMORY_MB: Final[int] = 512

_SOURCE_MODULE_NAME: Final[str] = "module_under_test"
_TEST_MODULE_NAME: Final[str] = "test_module_under_test"


class SandboxExecutionResult(
    BaseModel
):  # Result of running a pytest suite against a source module in an isolated sandbox.

    passed: bool  # True if all tests passed, False if any failed or if the sandbox execution itself failed.
    returncode: int | None = (
        None  # exit code if pytest completed, None if it timed out or failed to start
    )
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = Field(ge=0.0)
    error_message: str | None = (
        None  # sandbox execution error message (if any), e.g. timeout, OSError, etc.
    )


def _truncate_tail(  # truncates to the last part of the message since the beginning is often boilerplate
    text: str,
    max_chars: int = MAX_OUTPUT_CHARS,
    max_lines: int = MAX_OUTPUT_LINES,
) -> str:
    if not text:
        return text

    lines = text.splitlines()
    truncated_by_lines = len(lines) > max_lines
    if truncated_by_lines:
        lines = lines[-max_lines:]
    tail = "\n".join(lines)

    truncated_by_chars = len(tail) > max_chars
    if truncated_by_chars:
        tail = tail[-max_chars:]

    if truncated_by_lines or truncated_by_chars:
        tail = f"...[truncated]...\n{tail}"

    return tail


def _sanitize_test_imports(
    test_code: str,
) -> (
    str
):  # replaces any imports of the source module with a comment, to avoid accidental circular imports or other issues in the generated test code.
    sanitized_lines = []
    for line in test_code.splitlines():
        stripped = line.strip()
        looks_like_source_import = stripped.startswith(
            ("from .", f"from {_SOURCE_MODULE_NAME}", f"import {_SOURCE_MODULE_NAME}")
        )
        if looks_like_source_import:
            sanitized_lines.append(f"# [patchwork:stripped] {line}")
        else:
            sanitized_lines.append(line)
    return "\n".join(sanitized_lines)


def _limit_subprocess_memory() -> (
    None
):  # sets a hard limit on the subprocess's virtual memory usage to prevent runaway processes from consuming too much RAM. Only works on POSIX systems (Linux, macOS). Windows is not supported and will ignore this function.
    import resource  # imported lazily so Windows never touches it.

    limit_bytes = MAX_MEMORY_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))


def run_pytest_sandbox(
    source_code: str,
    test_code: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> (
    SandboxExecutionResult
):  # executes a generated pytest suite against generated source code in an isolated, disposable temporary directory.
    if timeout_sec <= 0:
        raise ValueError(f"timeout_sec must be positive, got {timeout_sec!r}")

    start_time = time.perf_counter()

    with tempfile_dir() as tmp_path:
        source_path = tmp_path / f"{_SOURCE_MODULE_NAME}.py"
        test_path = tmp_path / f"{_TEST_MODULE_NAME}.py"

        sanitized_test_code = _sanitize_test_imports(test_code)
        full_test_content = (
            "import sys\n"
            f"sys.path.insert(0, {str(tmp_path)!r})\n"
            f"from {_SOURCE_MODULE_NAME} import *  # noqa: F401,F403\n\n"
            f"{sanitized_test_code}\n"
        )

        try:
            source_path.write_text(source_code, encoding="utf-8")
            test_path.write_text(full_test_content, encoding="utf-8")
        except OSError as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                "sandbox_write_failed",
                extra={"event": "sandbox_write_failed", "error": str(exc)},
            )
            return SandboxExecutionResult(
                passed=False,
                duration_sec=duration,
                error_message=f"Failed to write sandbox files: {exc}",
            )

        preexec = _limit_subprocess_memory if platform.system() != "Windows" else None

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", str(test_path)],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=str(tmp_path),
                preexec_fn=preexec,
                check=False,  # non-zero exit (test failures) is an expected outcome, not an error
            )
            duration = time.perf_counter() - start_time
            passed = proc.returncode == 0
            logger.info(
                "sandbox_run_complete",
                extra={
                    "event": "sandbox_run_complete",
                    "passed": passed,
                    "returncode": proc.returncode,
                    "duration_sec": round(duration, 3),
                },
            )
            return SandboxExecutionResult(
                passed=passed,
                returncode=proc.returncode,
                timed_out=False,
                stdout=_truncate_tail(proc.stdout),
                stderr=_truncate_tail(proc.stderr),
                duration_sec=duration,
            )

        except subprocess.TimeoutExpired as exc:
            duration = time.perf_counter() - start_time
            logger.warning(
                "sandbox_run_timeout",
                extra={"event": "sandbox_run_timeout", "timeout_sec": timeout_sec},
            )
            raw_stdout = exc.stdout
            raw_stderr = exc.stderr
            partial_stdout = (
                raw_stdout.decode("utf-8", errors="replace")
                if isinstance(raw_stdout, bytes)
                else (raw_stdout or "")
            )
            partial_stderr = (
                raw_stderr.decode("utf-8", errors="replace")
                if isinstance(raw_stderr, bytes)
                else (raw_stderr or "")
            )
            return SandboxExecutionResult(
                passed=False,
                timed_out=True,
                stdout=_truncate_tail(partial_stdout),
                stderr=_truncate_tail(partial_stderr),
                duration_sec=duration,
                error_message=f"Execution exceeded {timeout_sec}s timeout.",
            )

        except FileNotFoundError as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                "sandbox_pytest_not_found",
                extra={"event": "sandbox_pytest_not_found", "error": str(exc)},
            )
            return SandboxExecutionResult(
                passed=False,
                duration_sec=duration,
                error_message=f"pytest executable not found: {exc}",
            )


def tempfile_dir():  # context manager that yields a temporary directory path and automatically cleans it up afterward. This is used to create an isolated sandbox for running tests without leaving any files behind.
    import tempfile
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        with tempfile.TemporaryDirectory(prefix="patchwork_sandbox_") as tmpdir:
            yield Path(tmpdir)

    return _cm()
