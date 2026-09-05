"""
tests/test_graph.py
=====================
All tests here mock structured_llm.invoke -- none of them touch a real
Ollama server or GPU, so this file runs fine in CI. Real-model testing
is a manual/local step, not something CI can rely on having a GPU for.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from patchwork.graph import (
    _build_audit_prompt,
    build_patchwork_graph,
    make_audit_and_generate_node,
    node_execute_tests,
    node_static_analysis,
)
from patchwork.state import CodeAuditOutput, create_initial_state


def _mock_llm(result: CodeAuditOutput) -> MagicMock:
    mock = MagicMock()
    mock.invoke.return_value = result
    return mock


class TestBuildAuditPrompt:
    def test_includes_source_code(self) -> None:
        state = create_initial_state("target.py", "def f():\n    pass\n")
        prompt = _build_audit_prompt(state)
        assert "def f():" in prompt

    def test_reports_no_lint_issues_when_none_present(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        state = node_static_analysis(state)
        prompt = _build_audit_prompt(state)
        assert "Linter issues: none" in prompt

    def test_includes_lint_issue_details(self) -> None:
        state = create_initial_state("target.py", "import os\n")
        state = node_static_analysis(state)
        prompt = _build_audit_prompt(state)
        assert "F401" in prompt


class TestNodeStaticAnalysis:
    def test_populates_ast_and_lint_results(self) -> None:
        state = create_initial_state("target.py", "def f():\n    pass\n")
        new_state = node_static_analysis(state)
        assert new_state["ast_result"] is not None
        assert new_state["lint_result"] is not None
        assert new_state["ast_result"].syntax_valid is True

    def test_does_not_mutate_input_state(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        original_trail_len = len(state["audit_trail"])
        node_static_analysis(state)
        assert len(state["audit_trail"]) == original_trail_len  # unchanged

    def test_appends_to_audit_trail_not_replaces(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        new_state = node_static_analysis(state)
        assert len(new_state["audit_trail"]) == len(state["audit_trail"]) + 1


class TestAuditAndGenerateNode:
    def test_successful_generation_updates_code_and_tests(self) -> None:
        mock_result = CodeAuditOutput(
            identified_bugs=["bug"],
            suggested_patch="def f():\n    return 1\n",
            pytest_suite="def test_f():\n    assert f() == 1\n",
        )
        node = make_audit_and_generate_node(_mock_llm(mock_result))
        state = create_initial_state("target.py", "def f():\n    return 0\n")

        new_state = node(state)

        assert new_state["current_code"] == mock_result.suggested_patch
        assert new_state["current_tests"] == mock_result.pytest_suite

    def test_schema_validation_failure_does_not_crash_node(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = ValidationError.from_exception_data(
            "CodeAuditOutput", []
        )
        node = make_audit_and_generate_node(mock_llm)
        state = create_initial_state("target.py", "x = 1")

        new_state = node(state)  # must not raise

        assert new_state["current_code"] == "x = 1"  # unchanged from original
        assert "failed" in new_state["audit_trail"][-1].lower()

    def test_output_parser_exception_does_not_crash_node(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = OutputParserException("could not parse")
        node = make_audit_and_generate_node(mock_llm)
        state = create_initial_state("target.py", "x = 1")

        new_state = node(state)  # must not raise

        assert new_state["current_code"] == "x = 1"

    def test_does_not_mutate_input_state(self) -> None:
        mock_result = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="y = 2",
            pytest_suite="def test_y():\n    assert y == 2\n",
        )
        node = make_audit_and_generate_node(_mock_llm(mock_result))
        state = create_initial_state("target.py", "x = 1")

        node(state)

        assert state["current_code"] == "x = 1"  # original state dict untouched


class TestNodeExecuteTests:
    def test_passing_generated_tests_report_passed(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a + b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"

        new_state = node_execute_tests(state)

        assert new_state["sandbox_result"] is not None
        assert new_state["sandbox_result"].passed is True

    def test_failing_generated_tests_report_not_passed(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"

        new_state = node_execute_tests(state)

        assert new_state["sandbox_result"].passed is False


class TestBuildPatchworkGraphIntegration:
    """Full graph run, mocked LLM, real ast_inspector/linter/sandbox calls."""

    def test_full_pass_with_passing_patch(self) -> None:
        mock_result = CodeAuditOutput(
            identified_bugs=["used + instead of /"],
            suggested_patch="def divide(a, b):\n    return a / b\n",
            pytest_suite="def test_divide():\n    assert divide(10, 2) == 5\n",
        )
        graph = build_patchwork_graph(_mock_llm(mock_result))
        initial = create_initial_state(
            "target.py", "def divide(a, b):\n    return a + b\n"
        )

        final = graph.invoke(initial)

        assert final["sandbox_result"].passed is True
        assert final["current_code"] == mock_result.suggested_patch
        assert (
            len(final["audit_trail"]) == 4
        )  # start + static_analysis + generate + execute

    def test_full_pass_with_schema_failure_still_completes(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = OutputParserException("truncated json")
        graph = build_patchwork_graph(mock_llm)
        initial = create_initial_state("target.py", "x = 1")

        final = graph.invoke(initial)  # must not raise, graph still reaches END

        assert final["current_code"] == "x = 1"
        assert final["sandbox_result"] is not None  # execute_tests still ran