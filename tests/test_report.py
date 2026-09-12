"""
tests/test_report.py
=======================
Pure function tests -- build_audit_report takes an AgentState and
returns a Markdown string, no I/O, no LLM, no subprocess mocking needed
beyond what node_static_analysis/node_execute_tests already produce via
real ast/ruff/pytest calls (same pattern as test_graph.py).
"""

from __future__ import annotations

from patchwork.graph import node_execute_tests, node_static_analysis
from patchwork.report import build_audit_report
from patchwork.state import create_initial_state


class TestBuildAuditReport:
    def test_includes_source_file_path_in_heading(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        report = build_audit_report(state)
        assert "target.py" in report

    def test_reports_tests_passed_true(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a + b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"
        state = node_execute_tests(state)

        report = build_audit_report(state)

        assert "Tests passed: True" in report

    def test_reports_tests_passed_false(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"
        state = node_execute_tests(state)

        report = build_audit_report(state)

        assert "Tests passed: False" in report

    def test_reports_na_when_no_sandbox_result_yet(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        report = build_audit_report(state)
        assert "Tests passed: N/A" in report

    def test_includes_retry_count_and_ceiling(self) -> None:
        state = create_initial_state("target.py", "x = 1", max_retries=3)
        state["retry_count"] = 2
        report = build_audit_report(state)
        assert "2 / 3" in report

    def test_diff_shows_no_changes_when_code_unmodified(self) -> None:
        state = create_initial_state("target.py", "x = 1\n")
        report = build_audit_report(state)
        assert "_No changes._" in report

    def test_diff_shows_added_and_removed_lines_when_code_changed(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_code"] = "def add(a, b):\n    return a + b\n"
        report = build_audit_report(state)
        assert "-    return a - b" in report
        assert "+    return a + b" in report

    def test_includes_lint_comparison_before_and_after(self) -> None:
        # before: unused import (F401). after: clean.
        state = create_initial_state("target.py", "import os\n")
        state["current_code"] = "x = 1\n"
        report = build_audit_report(state)
        assert "Before: 1 issue(s)" in report
        assert "After: 0 issue(s)" in report

    def test_includes_failure_output_when_tests_fail(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"
        state = node_execute_tests(state)

        report = build_audit_report(state)

        assert "AssertionError" in report or "assert" in report

    def test_includes_all_audit_trail_entries_numbered(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        state = node_static_analysis(state)
        report = build_audit_report(state)
        assert "1. Audit started for target.py" in report
        assert "2. Static analysis:" in report

    def test_report_is_a_string(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        report = build_audit_report(state)
        assert isinstance(report, str)
        assert len(report) > 0
