"""
tests/test_graph.py
=====================
All tests here mock structured_llm.invoke -- none of them touch a real
Ollama server or GPU, so this file runs fine in CI. Real-model testing
is a manual/local step, not something CI can rely on having a GPU for.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from patchwork.graph import (
    DEFAULT_MODEL,
    DEFAULT_NUM_CTX,
    DEFAULT_NUM_PREDICT,
    DEFAULT_REPEAT_PENALTY,
    DEFAULT_TEMPERATURE,
    LlmCallTimeoutError,
    _build_audit_prompt,
    _build_reflect_prompt,
    _invoke_with_timeout,
    build_patchwork_graph,
    build_structured_llm,
    make_audit_and_generate_node,
    make_reflect_and_heal_node,
    node_execute_tests,
    node_static_analysis,
    route_after_execution,
)
from patchwork.state import CodeAuditOutput, create_initial_state


def _mock_llm(result: CodeAuditOutput) -> MagicMock:
    mock = MagicMock()
    mock.invoke.return_value = result
    return mock


class TestBuildStructuredLlm:
    """Mocks ChatOllama itself -- never opens a real connection to Ollama."""

    @patch("patchwork.graph.ChatOllama")
    def test_builds_with_default_params(self, mock_chat_ollama: MagicMock) -> None:
        mock_llm_instance = MagicMock()
        mock_chat_ollama.return_value = mock_llm_instance

        build_structured_llm()

        mock_chat_ollama.assert_called_once_with(
            model=DEFAULT_MODEL,
            temperature=DEFAULT_TEMPERATURE,
            repeat_penalty=DEFAULT_REPEAT_PENALTY,
            num_ctx=DEFAULT_NUM_CTX,
            num_predict=DEFAULT_NUM_PREDICT,
        )
        mock_llm_instance.with_structured_output.assert_called_once_with(
            CodeAuditOutput
        )

    @patch("patchwork.graph.ChatOllama")
    def test_builds_with_custom_params(self, mock_chat_ollama: MagicMock) -> None:
        mock_llm_instance = MagicMock()
        mock_chat_ollama.return_value = mock_llm_instance

        build_structured_llm(
            model="custom:model",
            temperature=0.5,
            repeat_penalty=0.9,
            num_ctx=4096,
            num_predict=1024,
        )

        mock_chat_ollama.assert_called_once_with(
            model="custom:model",
            temperature=0.5,
            repeat_penalty=0.9,
            num_ctx=4096,
            num_predict=1024,
        )


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

    def test_syntax_errors_surface_via_linter_not_a_separate_note(self) -> None:
        # _build_audit_prompt no longer computes its own "Syntax status:"
        # line -- ruff's own invalid-syntax diagnostic (surfaced through
        # lint_result.issues, same as any other lint finding) is now the
        # only signal the prompt carries for unparseable source. Covers
        # what used to be the "INVALID SYNTAX" branch under the new,
        # simplified prompt.
        state = create_initial_state("target.py", "def broken(:\n    pass\n")
        state = node_static_analysis(state)
        prompt = _build_audit_prompt(state)
        assert "invalid-syntax" in prompt


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

    def test_node_handles_llm_call_timeout_without_crashing(self) -> None:
        # dependency-injected exception, not a real sleep/timeout race --
        # avoids the earlier flaw of trying to patch DEFAULT_LLM_TIMEOUT_SEC
        # after it was already bound as a function default argument
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = LlmCallTimeoutError("simulated timeout")
        node = make_audit_and_generate_node(mock_llm)
        state = create_initial_state("target.py", "x = 1")

        new_state = node(state)  # must not raise

        assert new_state["current_code"] == "x = 1"
        assert "failed" in new_state["audit_trail"][-1].lower()


class TestInvokeWithTimeout:
    def test_slow_call_raises_llm_call_timeout_error(self) -> None:
        import time

        def slow_invoke(prompt: str) -> CodeAuditOutput:
            time.sleep(0.5)
            return CodeAuditOutput(
                identified_bugs=[],
                suggested_patch="x = 1",
                pytest_suite="def test_x():\n    assert True",
            )

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = slow_invoke

        with pytest.raises(LlmCallTimeoutError):
            _invoke_with_timeout(mock_llm, "some prompt", timeout_sec=0.1)

    def test_fast_call_returns_normally(self) -> None:
        mock_result = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="x = 1",
            pytest_suite="def test_x():\n    assert True",
        )
        mock_llm = _mock_llm(mock_result)

        result = _invoke_with_timeout(mock_llm, "some prompt", timeout_sec=5.0)

        assert result == mock_result


class TestNodeExecuteTests:
    def test_passing_generated_tests_report_passed(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a + b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"

        new_state = node_execute_tests(state)

        sandbox_result = new_state["sandbox_result"]
        assert sandbox_result is not None
        assert sandbox_result.passed is True

    def test_failing_generated_tests_report_not_passed(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"

        new_state = node_execute_tests(state)

        sandbox_result = new_state["sandbox_result"]
        assert sandbox_result is not None
        assert sandbox_result.passed is False

    def test_blank_tests_are_skipped_not_executed(self) -> None:
        # new behavior: pytest_suite is no longer required to be non-empty
        # (see state.py), so node_execute_tests must handle "no tests
        # provided" as a distinct, non-crashing outcome rather than
        # running an empty suite through the sandbox
        state = create_initial_state("target.py", "x = 1")
        state["current_tests"] = "   "

        new_state = node_execute_tests(state)

        assert new_state["sandbox_result"] is None
        assert "skipped" in new_state["audit_trail"][-1].lower()


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

        sandbox_result = final["sandbox_result"]
        assert sandbox_result is not None
        assert sandbox_result.passed is True
        assert final["current_code"] == mock_result.suggested_patch
        assert (
            len(final["audit_trail"]) == 5
        )  # start + static_analysis + generate + execute + compile_report

    def test_full_pass_with_schema_failure_still_completes(self) -> None:
        # updated: on schema failure, current_tests stays "" (unchanged
        # from create_initial_state's default), so node_execute_tests now
        # takes the skip branch instead of running the sandbox --
        # sandbox_result correctly stays None, it does NOT get populated
        # as it did under the old always-run-the-sandbox behavior
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = OutputParserException("truncated json")
        graph = build_patchwork_graph(mock_llm)
        initial = create_initial_state("target.py", "x = 1")

        final = graph.invoke(initial)  # must not raise, graph still reaches END

        assert final["current_code"] == "x = 1"
        assert final["sandbox_result"] is None
        assert "skipped" in final["audit_trail"][-1].lower() or any(
            "skipped" in entry.lower() for entry in final["audit_trail"]
        )


class TestBuildReflectPrompt:
    def test_includes_diagnostics_and_current_code(self) -> None:
        # updated: the reflect prompt no longer echoes current_tests back
        # to the model (see graph.py) -- only current_code and the
        # failure diagnostics are included, so this no longer asserts on
        # a "Current tests:" section that doesn't exist anymore
        state = create_initial_state("target.py", "def f():\n    return 1\n")
        state["current_tests"] = "def test_f():\n    assert f() == 2\n"
        state = node_execute_tests(state)  # real sandbox run -> real failure output

        prompt = _build_reflect_prompt(state)

        assert "Failure Diagnostics:" in prompt
        assert "Current code:" in prompt
        assert "def f():" in prompt

    def test_handles_missing_sandbox_result_gracefully(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        prompt = _build_reflect_prompt(state)
        assert "unknown failure" in prompt


class TestReflectAndHealNode:
    def test_successful_reflection_updates_code_and_increments_retry(self) -> None:
        mock_result = CodeAuditOutput(
            identified_bugs=["fixed the off-by-one"],
            suggested_patch="def f():\n    return 2\n",
            pytest_suite="def test_f():\n    assert f() == 2\n",
        )
        node = make_reflect_and_heal_node(_mock_llm(mock_result))
        state = create_initial_state("target.py", "def f():\n    return 1\n")
        state["retry_count"] = 0

        new_state = node(state)

        assert new_state["current_code"] == mock_result.suggested_patch
        assert new_state["retry_count"] == 1

    def test_schema_failure_still_increments_retry_without_crashing(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = ValidationError.from_exception_data(
            "CodeAuditOutput", []
        )
        node = make_reflect_and_heal_node(mock_llm)
        state = create_initial_state("target.py", "x = 1")
        state["retry_count"] = 1

        new_state = node(state)  # must not raise

        assert new_state["retry_count"] == 2
        assert new_state["current_code"] == "x = 1"  # unchanged

    def test_does_not_mutate_input_state(self) -> None:
        mock_result = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="y = 2",
            pytest_suite="def test_y():\n    assert y == 2\n",
        )
        node = make_reflect_and_heal_node(_mock_llm(mock_result))
        state = create_initial_state("target.py", "x = 1")

        node(state)

        assert state["current_code"] == "x = 1"
        assert state["retry_count"] == 0


class TestRouteAfterExecution:
    def test_passing_tests_route_to_end(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a + b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"
        state = node_execute_tests(state)

        assert route_after_execution(state) == "end"

    def test_failing_tests_with_retries_remaining_route_to_reflect(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"
        state = node_execute_tests(state)
        state["retry_count"] = 0
        state["max_retries"] = 3

        assert route_after_execution(state) == "reflect"

    def test_failing_tests_with_retries_exhausted_route_to_end(self) -> None:
        state = create_initial_state("target.py", "def add(a, b):\n    return a - b\n")
        state["current_tests"] = "def test_add():\n    assert add(1, 2) == 3\n"
        state = node_execute_tests(state)
        state["retry_count"] = 3
        state["max_retries"] = 3

        assert route_after_execution(state) == "end"

    def test_no_sandbox_result_yet_routes_to_reflect_if_retries_remain(self) -> None:
        state = create_initial_state("target.py", "x = 1")
        assert route_after_execution(state) == "reflect"


class TestReflectionLoopIntegration:
    """Full graph run proving the loop actually loops and terminates."""

    def test_loop_converges_after_two_failed_attempts(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            CodeAuditOutput(
                identified_bugs=["v1"],
                suggested_patch="def divide(a, b):\n    return a - b\n",
                pytest_suite="def test_divide():\n    assert divide(10, 2) == 5\n",
            ),
            CodeAuditOutput(
                identified_bugs=["v2"],
                suggested_patch="def divide(a, b):\n    return a * b\n",
                pytest_suite="def test_divide():\n    assert divide(10, 2) == 5\n",
            ),
            CodeAuditOutput(
                identified_bugs=["v3 fixed"],
                suggested_patch="def divide(a, b):\n    return a / b\n",
                pytest_suite="def test_divide():\n    assert divide(10, 2) == 5\n",
            ),
        ]
        graph = build_patchwork_graph(mock_llm)
        initial = create_initial_state(
            "target.py", "def divide(a, b):\n    return a + b\n", max_retries=3
        )

        final = graph.invoke(initial)

        sandbox_result = final["sandbox_result"]
        assert sandbox_result is not None
        assert sandbox_result.passed is True
        assert final["retry_count"] == 2
        assert mock_llm.invoke.call_count == 3  # 1 initial generate + 2 reflects

    def test_loop_stops_at_max_retries_without_hanging(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = CodeAuditOutput(
            identified_bugs=["never fixed"],
            suggested_patch="def divide(a, b):\n    return a - b\n",
            pytest_suite="def test_divide():\n    assert divide(10, 2) == 5\n",
        )
        graph = build_patchwork_graph(mock_llm)
        initial = create_initial_state(
            "target.py", "def divide(a, b):\n    return a + b\n", max_retries=2
        )

        final = graph.invoke(initial)

        sandbox_result = final["sandbox_result"]
        assert sandbox_result is not None
        assert sandbox_result.passed is False
        assert final["retry_count"] == 2  # stopped exactly at the ceiling
        assert (
            mock_llm.invoke.call_count == 3
        )  # 1 initial generate + 2 reflects, then stop
