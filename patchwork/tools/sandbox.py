from __future__ import annotations

import logging
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

logger = logging.getLogger("patchwork.tools.sandbox")

DEFAULT_TIMEOUT_SEC: Final[int] = 10
MAX_OUTPUT_CHARS: Final[int] = 1000
MAX_OUTPUT_LINES: Final[int] = 20
MAX_MEMORY_MB: Final[int] = 512

_SOURCE_MODULE_NAME: Final[str] = "module_under_test"
_TEST_MODULE_NAME: Final[str] = "test_module_under_test"


class SandboxExecutionResult(BaseModel):
    """Strictly-typed result of a single sandboxed pytest run."""

    passed: bool
    returncode: int | None = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = Field(ge=0.0)
    error_message: str | None = None


def _truncate_tail(
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
    test_code: str, source_module_name: str | None = None
) -> str:
    patterns = [
        "from .",
        f"from {_SOURCE_MODULE_NAME}",
        f"import {_SOURCE_MODULE_NAME}",
    ]
    if source_module_name:
        mod = source_module_name.removesuffix(".py")
        patterns.extend([f"from {mod}", f"import {mod}"])
    target_prefixes = tuple(patterns)

    sanitized_lines = []
    for line in test_code.splitlines():
        if line.strip().startswith(target_prefixes):
            sanitized_lines.append(f"# [patchwork:stripped] {line}")
        else:
            sanitized_lines.append(line)
    return "\n".join(sanitized_lines)


def _limit_subprocess_memory() -> None:
    import resource  # POSIX-only; imported lazily so Windows never touches it.

    limit_bytes = MAX_MEMORY_MB * 1024 * 1024
    # mypy on Windows has no `resource` stub at all (module doesn't exist
    # there) -- this function is only ever called on POSIX, guarded by
    # platform.system() at the call site, but mypy checks function bodies
    # statically regardless of that runtime guard. Safe to ignore here.
    resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))  # type: ignore[attr-defined, unused-ignore]


@contextmanager
def tempfile_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="patchwork_sandbox_") as tmpdir:
        yield Path(tmpdir)


def run_pytest_sandbox(
    source_code: str,
    test_code: str,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    source_module_name: str | None = None,
) -> SandboxExecutionResult:
    """Executes a generated pytest suite against source code in an isolated temp directory."""
    if timeout_sec <= 0:
        raise ValueError(f"timeout_sec must be positive, got {timeout_sec!r}")

    start_time = time.perf_counter()

    with tempfile_dir() as tmp_path:
        source_path = tmp_path / f"{_SOURCE_MODULE_NAME}.py"
        test_path = tmp_path / f"{_TEST_MODULE_NAME}.py"

        sanitized_test_code = _sanitize_test_imports(
            test_code, source_module_name=source_module_name
        )
        full_test_content = (
            "import sys\n"
            f"sys.path.insert(0, {str(tmp_path)!r})\n"
            f"import {_SOURCE_MODULE_NAME}\n"
            f"for _sym in dir({_SOURCE_MODULE_NAME}):\n"
            "    if not _sym.startswith('__'):\n"
            f"        globals()[_sym] = getattr({_SOURCE_MODULE_NAME}, _sym)\n\n"
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
