"""patchwork.graph."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Final, Literal, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_ollama import ChatOllama
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from patchwork.report import build_audit_report
from patchwork.state import AgentState, CodeAuditOutput
from patchwork.tools.ast_inspector import inspect_source
from patchwork.tools.linter import run_ruff_linter
from patchwork.tools.sandbox import run_pytest_sandbox

logger = logging.getLogger("patchwork.graph")

DEFAULT_MODEL: Final[str] = "qwen2.5-coder:3b"
DEFAULT_TEMPERATURE: Final[float] = 0.2
DEFAULT_REPEAT_PENALTY: Final[float] = 1.15
DEFAULT_NUM_CTX: Final[int] = 8192
DEFAULT_NUM_PREDICT: Final[int] = 1024
DEFAULT_LLM_TIMEOUT_SEC: Final[float] = 45.0

SYSTEM_PROMPT: Final[str] = (
    "You are an expert Python engineer and automated code repair agent.\n"
    "Your job is to fix bugs accurately and concisely.\n\n"
    "Strict output constraints:\n"
    "1. NEVER output only a function header (e.g. `def foo():`). You MUST include the full indented function body.\n"
    "2. Never generate repetitive, duplicate, or combinatorial test cases.\n"
    "3. Limit `pytest_suite` to at most 2 targeted assertions (1 happy path, 1 boundary condition).\n"
    "4. Keep `suggested_patch` strictly to the repaired function/class. Never include test functions inside `suggested_patch`.\n"
    "5. Return clean, parseable structured data without extra commentary."
)

_llm_timeout_executor: Final[ThreadPoolExecutor] = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="patchwork-llm-call"
)


def build_structured_llm(
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    repeat_penalty: float = DEFAULT_REPEAT_PENALTY,
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: int = DEFAULT_NUM_PREDICT,
) -> Runnable[str, CodeAuditOutput]:
    llm = ChatOllama(
        model=model,
        temperature=temperature,
        repeat_penalty=repeat_penalty,
        num_ctx=num_ctx,
        num_predict=num_predict,
    )

    structured_llm = llm.with_structured_output(CodeAuditOutput)

    def _format_messages(user_prompt: str) -> list[SystemMessage | HumanMessage]:
        return [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

    chain = RunnableLambda(_format_messages) | structured_llm
    return cast(Runnable[str, CodeAuditOutput], chain)


class LlmCallTimeoutError(Exception):
    """Raised when an LLM call exceeds the wall-clock timeout."""


def _invoke_with_timeout(
    structured_llm: Runnable[str, CodeAuditOutput],
    prompt: str,
    timeout_sec: float = DEFAULT_LLM_TIMEOUT_SEC,
) -> CodeAuditOutput:
    future = _llm_timeout_executor.submit(structured_llm.invoke, prompt)
    try:
        return future.result(timeout=timeout_sec)
    except FutureTimeoutError as exc:
        raise LlmCallTimeoutError(
            f"structured_llm.invoke() exceeded {timeout_sec}s timeout"
        ) from exc


def _build_audit_prompt(state: AgentState) -> str:
    lint_summary = "none"
    if state["lint_result"] is not None and state["lint_result"].issues:
        lint_summary = "; ".join(
            f"line {issue.line}: {issue.code} {issue.message}"
            for issue in state["lint_result"].issues
        )

    return (
        "You are an expert Python bug fixer.\n"
        f"Linter issues: {lint_summary}\n\n"
        f"Source code:\n```python\n{state['current_code']}\n```\n\n"
        "Instructions:\n"
        "1. `suggested_patch`: Provide the FULL, complete Python code with body implementation.\n"
        "   - NEVER output only the function signature line.\n"
        "   - NEVER put test functions (`def test_...`) inside suggested_patch.\n"
        "   - If the code is already correct, output the original code exactly.\n"
        "2. `pytest_suite`: Provide EXACTLY 2 concise unit tests using pytest.\n"
        "   - Test 1: Standard expected behavior.\n"
        "   - Test 2: Edge/boundary case that exposes defects (e.g. NoneType, float precision, empty containers).\n"
        "   - Do NOT output more than 2 test functions."
    )


def _build_reflect_prompt(state: AgentState) -> str:
    sandbox = state["sandbox_result"]
    failure_output = (
        sandbox.stderr
        if sandbox and sandbox.stderr
        else (sandbox.stdout if sandbox else "unknown failure")
    )

    schema_warning = ""
    if state.get("last_error"):
        schema_warning = (
            "CRITICAL PREVIOUS ERROR:\n"
            f"{state['last_error']}\n"
            "You MUST fix this formatting/implementation issue.\n\n"
        )

    return (
        f"{schema_warning}"
        "The previous patch failed verification.\n\n"
        f"Failure Diagnostics:\n{failure_output}\n\n"
        f"Current code:\n```python\n{state['current_code']}\n```\n\n"
        "Instructions:\n"
        "1. `suggested_patch`: Provide the FULL, repaired Python code with indented body.\n"
        "   - NEVER output just the signature line.\n"
        "   - Fix the root cause identified in the diagnostics.\n"
        "2. `pytest_suite`: EXACTLY 2 minimal pytest assertions that verify this specific fix."
    )


def node_static_analysis(state: AgentState) -> AgentState:
    ast_result = inspect_source(state["current_code"])
    lint_result = run_ruff_linter(state["current_code"])

    trail_entry = f"Static analysis: syntax_valid={ast_result.syntax_valid}, {lint_result.issue_count_total} lint issues"
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
            result = _invoke_with_timeout(structured_llm, prompt)
        except (ValidationError, OutputParserException, LlmCallTimeoutError) as exc:
            err_msg = str(exc)
            logger.warning("audit_generation_failed", extra={"error": err_msg})
            return {
                **state,
                "last_error": f"Schema parsing failed: {err_msg}",
                "audit_trail": [
                    *state["audit_trail"],
                    f"Audit generation failed schema validation: {err_msg}",
                ],
            }

        patch = (
            state["original_code"]
            if result.suggested_patch == "PASS_UNCHANGED"
            else result.suggested_patch
        )

        trail_entry = f"Generated patch and tests. Bugs identified: {result.identified_bugs or 'none reported'}"
        return {
            **state,
            "current_code": patch,
            "current_tests": result.pytest_suite,
            "last_error": None,
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
            result = _invoke_with_timeout(structured_llm, prompt)
        except (ValidationError, OutputParserException, LlmCallTimeoutError) as exc:
            err_msg = str(exc)
            logger.warning("reflection_failed", extra={"error": err_msg})
            return {
                **state,
                "retry_count": next_retry_count,
                "last_error": f"Schema parsing failed: {err_msg}",
                "audit_trail": [
                    *state["audit_trail"],
                    f"Reflection attempt {next_retry_count} failed schema validation: {err_msg}",
                ],
            }

        patch = (
            state["current_code"]
            if result.suggested_patch == "PASS_UNCHANGED"
            else result.suggested_patch
        )

        trail_entry = f"Reflection attempt {next_retry_count}: patched code and tests based on failure output"
        return {
            **state,
            "current_code": patch,
            "current_tests": result.pytest_suite or state["current_tests"],
            "retry_count": next_retry_count,
            "last_error": None,
            "audit_trail": [*state["audit_trail"], trail_entry],
        }

    return node_reflect_and_heal


def node_execute_tests(state: AgentState) -> AgentState:
    if not state["current_tests"].strip():
        trail_entry = "Test execution: skipped (no tests provided)"
        return {
            **state,
            "audit_trail": [*state["audit_trail"], trail_entry],
        }

    # Execute tests against the patched code
    sandbox_result = run_pytest_sandbox(state["current_code"], state["current_tests"])

    trail_entry = f"Test execution: passed={sandbox_result.passed}, timed_out={sandbox_result.timed_out}"
    return {
        **state,
        "sandbox_result": sandbox_result,
        "audit_trail": [*state["audit_trail"], trail_entry],
    }


def node_compile_report(state: AgentState) -> AgentState:
    report = build_audit_report(state)
    trail_entry = "Compiled final audit report"
    return {
        **state,
        "report_markdown": report,
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
    workflow.add_node(
        "audit_and_generate",
        cast(Any, make_audit_and_generate_node(structured_llm)),
    )
    workflow.add_node("execute_tests", node_execute_tests)
    workflow.add_node(
        "reflect",
        cast(Any, make_reflect_and_heal_node(structured_llm)),
    )
    workflow.add_node("compile_report", node_compile_report)

    workflow.set_entry_point("static_analysis")
    workflow.add_edge("static_analysis", "audit_and_generate")
    workflow.add_edge("audit_and_generate", "execute_tests")
    workflow.add_conditional_edges(
        "execute_tests",
        route_after_execution,
        {"end": "compile_report", "reflect": "reflect"},
    )
    workflow.add_edge("reflect", "execute_tests")
    workflow.add_edge("compile_report", END)

    return workflow.compile()
