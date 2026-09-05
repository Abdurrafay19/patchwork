"""
patchwork.graph
=================
LangGraph workflow: static_analysis -> audit_and_generate -> execute_tests,
then conditionally either END (tests passed, or retries exhausted) or
reflect -> execute_tests again (tests failed, retries remain).

The SLM call is injected as a dependency (build_structured_llm / passed
into build_patchwork_graph) rather than instantiated at import time, so
tests can swap in a mock and never touch a real Ollama server.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final, Literal

from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import Runnable
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from patchwork.state import AgentState, CodeAuditOutput
from patchwork.tools.ast_inspector import inspect_source
from patchwork.tools.linter import run_ruff_linter
from patchwork.tools.sandbox import run_pytest_sandbox

logger = logging.getLogger("patchwork.graph")

DEFAULT_MODEL: Final[str] = "qwen2.5-coder:3b"
DEFAULT_TEMPERATURE: Final[float] = (
    0.1  # low temp -- 3B models hallucinate params at default 0.7-0.8
)
DEFAULT_NUM_CTX: Final[int] = (
    8192  # Ollama defaults to 2048, which silently truncates source+traceback
)


def build_structured_llm(
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> Runnable[str, CodeAuditOutput]:
    llm = ChatOllama(model=model, temperature=temperature, num_ctx=num_ctx)
    return llm.with_structured_output(CodeAuditOutput)  # type: ignore[return-value]


def _build_audit_prompt(state: AgentState) -> str:
    lint_summary = "none"
    if state["lint_result"] is not None and state["lint_result"].issues:
        lint_summary = "; ".join(
            f"line {issue.line}: {issue.code} {issue.message}"
            for issue in state["lint_result"].issues
        )

    syntax_note = (
        "valid"
        if state["ast_result"] is None or state["ast_result"].syntax_valid
        else "INVALID SYNTAX"
    )

    return (
        "Analyze this Python code, identify bugs, propose a complete patched version, "
        "and write a complete pytest suite covering the bugs you find.\n\n"
        f"Syntax status: {syntax_note}\n"
        f"Linter issues: {lint_summary}\n\n"
        f"Source code:\n```python\n{state['current_code']}\n```"
    )


def _build_reflect_prompt(state: AgentState) -> str:
    sandbox = state["sandbox_result"]
    # sandbox.stdout/stderr are already truncated to the last 20 lines /
    # 1000 chars by sandbox.py -- no extra truncation needed here.
    failure_output = (
        sandbox.stderr
        if sandbox and sandbox.stderr
        else (sandbox.stdout if sandbox else "unknown failure")
    )

    return (
        "The previous patch and test suite failed execution. Analyze the "
        "failure output below and fix BOTH the code and the tests so they "
        "pass deterministically.\n\n"
        f"Execution output:\n{failure_output}\n\n"
        f"Current code:\n```python\n{state['current_code']}\n```\n\n"
        f"Current tests:\n```python\n{state['current_tests']}\n```"
    )


def node_static_analysis(state: AgentState) -> AgentState:
    ast_result = inspect_source(state["current_code"])
    lint_result = run_ruff_linter(state["current_code"])

    trail_entry = f"Static analysis: syntax_valid={ast_result.syntax_valid}, {lint_result.issue_count_total} lint issues"
    logger.info(
        "node_static_analysis_complete",
        extra={"event": "node_static_analysis_complete"},
    )

    # never mutate the incoming state dict -- return a new one
    return {
        **state,
        "ast_result": ast_result,
        "lint_result": lint_result,
        "audit_trail": [*state["audit_trail"], trail_entry],
    }


def make_audit_and_generate_node(
    structured_llm: Runnable[str, CodeAuditOutput],
) -> Callable[[AgentState], AgentState]:
    def node_audit_and_generate(state: AgentState) -> AgentState:
        prompt = _build_audit_prompt(state)

        try:
            result = structured_llm.invoke(prompt)
        except (ValidationError, OutputParserException) as exc:
            # SLM returned something that didn't fit CodeAuditOutput (truncated
            # JSON, markdown-wrapped garbage that survived stripping, etc).
            # Don't crash the graph -- leave current_code/current_tests as-is
            # and let execute_tests report the failure downstream.
            logger.warning(
                "audit_generation_failed",
                extra={"event": "audit_generation_failed", "error": str(exc)},
            )
            return {
                **state,
                "audit_trail": [
                    *state["audit_trail"],
                    f"Audit generation failed schema validation: {exc}",
                ],
            }

        trail_entry = f"Generated patch and tests. Bugs identified: {result.identified_bugs or 'none reported'}"
        return {
            **state,
            "current_code": result.suggested_patch,
            "current_tests": result.pytest_suite,
            "audit_trail": [*state["audit_trail"], trail_entry],
        }

    return node_audit_and_generate


def make_reflect_and_heal_node(
    structured_llm: Runnable[str, CodeAuditOutput],
) -> Callable[[AgentState], AgentState]:
    def node_reflect_and_heal(state: AgentState) -> AgentState:
        next_retry_count = state["retry_count"] + 1
        prompt = _build_reflect_prompt(state)

        try:
            result = structured_llm.invoke(prompt)
        except (ValidationError, OutputParserException) as exc:
            # same failure mode as audit_and_generate -- don't crash, don't
            # touch current_code/current_tests, just burn the retry and
            # let route_after_execution decide whether to try again.
            logger.warning(
                "reflection_failed",
                extra={"event": "reflection_failed", "error": str(exc)},
            )
            return {
                **state,
                "retry_count": next_retry_count,
                "audit_trail": [
                    *state["audit_trail"],
                    f"Reflection attempt {next_retry_count} failed schema validation: {exc}",
                ],
            }

        trail_entry = f"Reflection attempt {next_retry_count}: patched code and tests based on failure output"
        return {
            **state,
            "current_code": result.suggested_patch,
            "current_tests": result.pytest_suite,
            "retry_count": next_retry_count,
            "audit_trail": [*state["audit_trail"], trail_entry],
        }

    return node_reflect_and_heal


def node_execute_tests(state: AgentState) -> AgentState:
    sandbox_result = run_pytest_sandbox(state["current_code"], state["current_tests"])
    trail_entry = f"Test execution: passed={sandbox_result.passed}, timed_out={sandbox_result.timed_out}"
    logger.info(
        "node_execute_tests_complete", extra={"event": "node_execute_tests_complete"}
    )

    return {
        **state,
        "sandbox_result": sandbox_result,
        "audit_trail": [*state["audit_trail"], trail_entry],
    }


def route_after_execution(state: AgentState) -> Literal["end", "reflect"]:
    sandbox = state["sandbox_result"]
    if sandbox is not None and sandbox.passed:
        return "end"
    if state["retry_count"] >= state["max_retries"]:
        return "end"
    return "reflect"


def build_patchwork_graph(
    structured_llm: Runnable[str, CodeAuditOutput],
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    workflow: StateGraph[AgentState, None, AgentState, AgentState] = StateGraph(
        AgentState
    )

    workflow.add_node("static_analysis", node_static_analysis)
    # langgraph's add_node overloads misresolve on closures (vs. plain
    # functions like node_static_analysis above) -- verified correct at
    # runtime via test_graph.py, this is a stub limitation, not a real bug.
    workflow.add_node(
        "audit_and_generate",
        make_audit_and_generate_node(structured_llm),  # type: ignore[arg-type]
    )
    workflow.add_node("execute_tests", node_execute_tests)
    workflow.add_node(
        "reflect",
        make_reflect_and_heal_node(structured_llm),  # type: ignore[arg-type]
    )

    workflow.set_entry_point("static_analysis")
    workflow.add_edge("static_analysis", "audit_and_generate")
    workflow.add_edge("audit_and_generate", "execute_tests")
    workflow.add_conditional_edges(
        "execute_tests",
        route_after_execution,
        {"end": END, "reflect": "reflect"},
    )
    workflow.add_edge("reflect", "execute_tests")

    return workflow.compile()