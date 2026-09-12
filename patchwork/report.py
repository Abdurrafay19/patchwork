"""
patchwork.report
==================
Builds the final Markdown audit report from a completed AgentState.

Pure function, no I/O -- node_compile_report in graph.py calls this and
stores the result in state; writing audit_report.md to disk is the
caller's job (cli.py, evaluate.py), matching the pure-function-plus-edge-IO
split already used by patchwork.tools.
"""

from __future__ import annotations

import difflib
from typing import Final

from patchwork.state import AgentState
from patchwork.tools.linter import run_ruff_linter

_DIFF_CONTEXT_LINES: Final[int] = 3


def _render_diff(original_code: str, current_code: str) -> str:
    diff_lines = difflib.unified_diff(
        original_code.splitlines(keepends=True),
        current_code.splitlines(keepends=True),
        fromfile="original",
        tofile="patched",
        n=_DIFF_CONTEXT_LINES,
    )
    diff_text = "".join(diff_lines)
    return diff_text if diff_text else "_No changes._"


def _render_lint_comparison(original_code: str, current_code: str) -> str:
    # re-runs the linter fresh on both versions rather than reusing
    # state["lint_result"] -- that field only ever holds the most recent
    # analysis of current_code, so it can't give a before/after comparison
    # on its own.
    before = run_ruff_linter(original_code)
    after = run_ruff_linter(current_code)
    before_count = before.issue_count_total if before.success else "N/A"
    after_count = after.issue_count_total if after.success else "N/A"
    return f"- Before: {before_count} issue(s)\n- After: {after_count} issue(s)"


def _render_test_summary(state: AgentState) -> str:
    sandbox = state["sandbox_result"]
    if sandbox is None:
        return "No test execution recorded."
    lines = [f"- Passed: {sandbox.passed}", f"- Timed out: {sandbox.timed_out}"]
    if not sandbox.passed:
        failure_output = sandbox.stderr or sandbox.stdout
        lines.append(f"\n```\n{failure_output}\n```")
    return "\n".join(lines)


def build_audit_report(state: AgentState) -> str:
    """Builds the full Markdown audit report for a completed run.

    Args:
        state: The final AgentState after the graph reaches its terminal
            edge (tests passed, or retries exhausted).

    Returns:
        A Markdown-formatted report string, ready to write to
        `audit_report.md`.
    """
    sandbox = state["sandbox_result"]
    sections = [
        f"# Audit Report: {state['source_file_path']}",
        "",
        "## Outcome",
        f"- Tests passed: {sandbox.passed if sandbox else 'N/A'}",
        f"- Reflection attempts used: {state['retry_count']} / {state['max_retries']}",
        "",
        "## Linter Issues (before vs after)",
        _render_lint_comparison(state["original_code"], state["current_code"]),
        "",
        "## Code Diff",
        f"```diff\n{_render_diff(state['original_code'], state['current_code'])}\n```",
        "",
        "## Test Execution",
        _render_test_summary(state),
        "",
        "## Audit Trail",
        *[f"{i}. {entry}" for i, entry in enumerate(state["audit_trail"], start=1)],
    ]
    return "\n".join(sections)
