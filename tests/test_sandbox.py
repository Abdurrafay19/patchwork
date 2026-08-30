"""
tests/test_sandbox.py
======================
Unit and integration tests for `patchwork.tools.sandbox`.

Two tiers:
    * `TestRunPytestSandboxMocked` -- fast, mocks `subprocess.run` so no
      real pytest process is ever spawned. Good for CI and for validating
      error-handling branches (timeouts, missing executable) that would
      be slow or flaky to trigger for real.
    * `TestRunPytestSandboxIntegration` -- slower, spawns real pytest
      subprocesses. Catches issues mocking would hide, like sys.path
      wiring and the import-sanitization heuristic.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from patchwork.tools.sandbox import (
    DEFAULT_TIMEOUT_SEC,
    SandboxExecutionResult,
    _sanitize_test_imports,
    _truncate_tail,
    run_pytest_sandbox,
)


class TestTruncateTail:
    def test_short_text_untouched(self) -> None:
        text = "line1\nline2"
        assert _truncate_tail(text) == text

    def test_truncates_by_line_count(self) -> None:
        text = "\n".join(f"line{i}" for i in range(50))
        result = _truncate_tail(text, max_chars=10_000, max_lines=5)
        assert result.startswith("...[truncated]...")
        assert result.count("\n") <= 6  # marker line + 5 kept lines

    def test_truncates_by_char_count(self) -> None:
        text = "x" * 5000
        result = _truncate_tail(text, max_chars=100, max_lines=1000)
        assert result.startswith("...[truncated]...")
        assert len(result) < 5000

    def test_empty_string(self) -> None:
        assert _truncate_tail("") == ""


class TestSanitizeTestImports:
    def test_strips_relative_import(self) -> None:
        code = "from .utils import helper\ndef test_x():\n    assert True"
        sanitized = _sanitize_test_imports(code)
        first_line = sanitized.split("\n")[0]
        assert first_line.startswith("# [patchwork:stripped]")

    def test_strips_module_under_test_import(self) -> None:
        code = "from module_under_test import foo\nassert foo"
        sanitized = _sanitize_test_imports(code)
        assert sanitized.startswith("# [patchwork:stripped]")

    def test_leaves_unrelated_imports_alone(self) -> None:
        code = "import math\ndef test_x():\n    assert math.pi > 3"
        sanitized = _sanitize_test_imports(code)
        assert sanitized == code


class TestRunPytestSandboxValidation:
    def test_zero_timeout_raises(self) -> None:
        with pytest.raises(ValueError):
            run_pytest_sandbox("x = 1", "def test_x():\n    assert True", timeout_sec=0)

    def test_negative_timeout_raises(self) -> None:
        with pytest.raises(ValueError):
            run_pytest_sandbox("x = 1", "def test_x():\n    assert True", timeout_sec=-5)


class TestRunPytestSandboxMocked:
    """Mocks subprocess.run -- no real pytest process is spawned here."""

    @patch("patchwork.tools.sandbox.subprocess.run")
    def test_passing_run_reports_passed(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="1 passed", stderr=""
        )
        result = run_pytest_sandbox(
            "def add(a, b):\n    return a + b",
            "def test_add():\n    assert add(1, 2) == 3",
        )
        assert isinstance(result, SandboxExecutionResult)
        assert result.passed is True
        assert result.returncode == 0
        assert result.timed_out is False

    @patch("patchwork.tools.sandbox.subprocess.run")
    def test_failing_run_reports_not_passed(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"], returncode=1, stdout="1 failed", stderr="AssertionError"
        )
        result = run_pytest_sandbox(
            "def add(a, b):\n    return a - b",
            "def test_add():\n    assert add(1, 2) == 3",
        )
        assert result.passed is False
        assert result.returncode == 1
        assert "failed" in result.stdout

    @patch("patchwork.tools.sandbox.subprocess.run")
    def test_timeout_expired_reports_timed_out(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["pytest"], timeout=10, output=b"partial", stderr=b""
        )
        result = run_pytest_sandbox(
            "x = 1",
            "def test_x():\n    while True:\n        pass",
            timeout_sec=1,
        )
        assert result.passed is False
        assert result.timed_out is True
        assert result.error_message is not None

    @patch("patchwork.tools.sandbox.subprocess.run")
    def test_pytest_not_found_reports_error_message(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("pytest not installed")
        result = run_pytest_sandbox("x = 1", "def test_x():\n    assert True")
        assert result.passed is False
        assert result.error_message is not None
        assert "pytest" in result.error_message.lower()

    @patch("patchwork.tools.sandbox.subprocess.run")
    def test_default_timeout_used_when_unspecified(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="ok", stderr=""
        )
        run_pytest_sandbox("x = 1", "def test_x():\n    assert True")
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == DEFAULT_TIMEOUT_SEC


class TestRunPytestSandboxIntegration:
    """Real, unmocked subprocess execution."""

    def test_real_passing_suite(self) -> None:
        source = "def multiply(a, b):\n    return a * b\n"
        tests = "def test_multiply():\n    assert multiply(3, 4) == 12\n"
        result = run_pytest_sandbox(source, tests, timeout_sec=15)
        assert result.passed is True
        assert result.timed_out is False

    def test_real_failing_suite(self) -> None:
        source = "def divide(a, b):\n    return a + b  # bug: should be a / b\n"
        tests = "def test_divide():\n    assert divide(10, 2) == 5\n"
        result = run_pytest_sandbox(source, tests, timeout_sec=15)
        assert result.passed is False
        assert result.returncode != 0

    def test_real_infinite_loop_times_out(self) -> None:
        source = "def noop():\n    return None\n"
        tests = "def test_hang():\n    while True:\n        pass\n"
        result = run_pytest_sandbox(source, tests, timeout_sec=2)
        assert result.passed is False
        assert result.timed_out is True

    def test_real_relative_import_is_sanitized(self) -> None:
        source = "def helper():\n    return 42\n"
        tests = "from .utils import helper\n\ndef test_helper():\n    assert helper() == 42\n"
        result = run_pytest_sandbox(source, tests, timeout_sec=15)
        # Must not crash with ModuleNotFoundError: the bad import line is
        # stripped, and the `import *` supplies `helper` instead.
        assert result.passed is True

    def test_result_is_pydantic_model_and_json_serializable(self) -> None:
        result = run_pytest_sandbox("x = 1", "def test_x():\n    assert True", timeout_sec=15)
        payload = result.model_dump_json()
        assert isinstance(payload, str)
        assert '"passed":true' in payload.replace(" ", "")