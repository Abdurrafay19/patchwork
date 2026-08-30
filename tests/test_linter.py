"""
tests/test_linter.py
======================
Unit and integration tests for `patchwork.tools.linter`.

Same two-tier structure as `test_sandbox.py`:
    * `TestRunRuffLinterMocked` -- mocks `subprocess.run`, no real ruff
      process spawned. Covers error-handling branches.
    * `TestRunRuffLinterIntegration` -- runs real `ruff check` subprocess
      calls against known-good and known-bad source strings.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from patchwork.tools.linter import (
    DEFAULT_TIMEOUT_SEC,
    LintRunResult,
    _parse_ruff_json,
    _truncate_message,
    run_ruff_linter,
)

_SAMPLE_RUFF_JSON = json.dumps(
    [
        {
            "cell": None,
            "code": "F401",
            "end_location": {"column": 10, "row": 1},
            "filename": "/tmp/x.py",
            "fix": {"applicability": "safe", "edits": [], "message": "Remove unused import"},
            "location": {"column": 8, "row": 1},
            "message": "`os` imported but unused",
            "name": "unused-import",
            "noqa_row": 1,
            "severity": "error",
            "url": "https://docs.astral.sh/ruff/rules/unused-import",
        }
    ]
)


class TestTruncateMessage:
    def test_short_message_untouched(self) -> None:
        assert _truncate_message("short message") == "short message"

    def test_long_message_truncated(self) -> None:
        message = "x" * 500
        result = _truncate_message(message, max_chars=50)
        assert result.endswith("...[truncated]")
        assert len(result) < 500


class TestParseRuffJson:
    def test_parses_well_formed_entries(self) -> None:
        issues = _parse_ruff_json(_SAMPLE_RUFF_JSON)
        assert len(issues) == 1
        assert issues[0].code == "F401"
        assert issues[0].line == 1
        assert issues[0].is_fixable is True

    def test_empty_array_returns_empty_list(self) -> None:
        assert _parse_ruff_json("[]") == []

    def test_invalid_json_raises_json_decode_error(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_ruff_json("not json at all")

    def test_skips_malformed_entry_without_crashing(self) -> None:
        malformed = json.dumps([{"unexpected": "shape"}])
        # location.get(...) on a missing key still works (defaults to {}),
        # message defaults to "", so this should NOT raise -- it should
        # produce a best-effort issue with line=0, column=0.
        issues = _parse_ruff_json(malformed)
        assert len(issues) == 1
        assert issues[0].line == 0


class TestRunRuffLinterValidation:
    def test_zero_timeout_raises(self) -> None:
        with pytest.raises(ValueError):
            run_ruff_linter("x = 1", timeout_sec=0)

    def test_negative_timeout_raises(self) -> None:
        with pytest.raises(ValueError):
            run_ruff_linter("x = 1", timeout_sec=-1)


class TestRunRuffLinterMocked:
    @patch("patchwork.tools.linter.subprocess.run")
    def test_clean_code_reports_success_no_issues(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"], returncode=0, stdout="[]", stderr=""
        )
        result = run_ruff_linter("x = 1\n")
        assert isinstance(result, LintRunResult)
        assert result.success is True
        assert result.issues == []
        assert result.issue_count_total == 0

    @patch("patchwork.tools.linter.subprocess.run")
    def test_dirty_code_reports_issues(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"], returncode=1, stdout=_SAMPLE_RUFF_JSON, stderr=""
        )
        result = run_ruff_linter("import os\n")
        assert result.success is True  # ruff ran fine; it just found issues
        assert len(result.issues) == 1
        assert result.issues[0].code == "F401"

    @patch("patchwork.tools.linter.subprocess.run")
    def test_timeout_expired_reports_timed_out(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ruff"], timeout=10)
        result = run_ruff_linter("x = 1", timeout_sec=1)
        assert result.success is False
        assert result.timed_out is True
        assert result.error_message is not None

    @patch("patchwork.tools.linter.subprocess.run")
    def test_ruff_not_found_reports_error_message(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("ruff not installed")
        result = run_ruff_linter("x = 1")
        assert result.success is False
        assert result.error_message is not None
        assert "ruff" in result.error_message.lower()

    @patch("patchwork.tools.linter.subprocess.run")
    def test_malformed_json_output_reports_error_message(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"], returncode=1, stdout="not valid json{{{", stderr=""
        )
        result = run_ruff_linter("x = 1")
        assert result.success is False
        assert result.error_message is not None

    @patch("patchwork.tools.linter.subprocess.run")
    def test_issues_truncated_beyond_max_retained(self, mock_run: MagicMock) -> None:
        many_issues = json.dumps(
            [
                {
                    "code": "F401",
                    "name": "unused-import",
                    "message": f"issue {i}",
                    "location": {"row": i, "column": 1},
                    "severity": "error",
                    "fix": None,
                }
                for i in range(50)
            ]
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"], returncode=1, stdout=many_issues, stderr=""
        )
        result = run_ruff_linter("x = 1")
        assert result.issue_count_total == 50
        assert len(result.issues) < 50  # truncated to MAX_ISSUES_RETAINED

    @patch("patchwork.tools.linter.subprocess.run")
    def test_default_timeout_used_when_unspecified(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"], returncode=0, stdout="[]", stderr=""
        )
        run_ruff_linter("x = 1")
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == DEFAULT_TIMEOUT_SEC


class TestRunRuffLinterIntegration:
    """Real (unmocked) ruff subprocess execution."""

    def test_real_clean_code_has_no_issues(self) -> None:
        source = "def add(a: int, b: int) -> int:\n    return a + b\n"
        result = run_ruff_linter(source, timeout_sec=15)
        assert result.success is True
        assert result.issues == []

    def test_real_unused_import_detected(self) -> None:
        source = "import os\n\n\ndef noop() -> None:\n    return None\n"
        result = run_ruff_linter(source, timeout_sec=15)
        assert result.success is True
        codes = [issue.code for issue in result.issues]
        assert "F401" in codes

    def test_real_mutable_default_argument_detected(self) -> None:
        source = "def append_item(item, target_list=[]):\n    target_list.append(item)\n    return target_list\n"
        result = run_ruff_linter(source, timeout_sec=15)
        assert result.success is True
        codes = [issue.code for issue in result.issues]
        assert "B006" in codes

    def test_real_syntax_error_reported_as_issue_not_crash(self) -> None:
        # Covers checklist item 5.1 "Unparseable Original Code": ruff
        # itself should not crash the tool -- it should surface the
        # syntax error as a normal issue instead. Older ruff versions
        # use the code "E999"; ruff >= 0.something renamed this to
        # "invalid-syntax". Accept either so this test isn't pinned to
        # one ruff release.
        source = "def broken(:\n    pass\n"
        result = run_ruff_linter(source, timeout_sec=15)
        assert result.success is True
        assert len(result.issues) > 0
        codes = [issue.code for issue in result.issues]
        assert any(code in ("E999", "invalid-syntax") for code in codes)

    def test_result_is_pydantic_model_and_json_serializable(self) -> None:
        result = run_ruff_linter("import sys\n", timeout_sec=15)
        payload = result.model_dump_json()
        assert isinstance(payload, str)
        assert '"success":true' in payload.replace(" ", "")