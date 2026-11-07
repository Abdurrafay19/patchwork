"""patchwork.state."""

from __future__ import annotations

import ast
import re
from typing import Final, TypedDict

from pydantic import BaseModel, Field, field_validator

from patchwork.tools.ast_inspector import ASTInspectionResult
from patchwork.tools.linter import LintRunResult
from patchwork.tools.sandbox import SandboxExecutionResult

DEFAULT_MAX_RETRIES: Final[int] = 3

NO_CHANGE_PHRASES: Final[tuple[str, ...]] = (
    "no changes needed",
    "already correct",
    "no bugs found",
    "no modifications needed",
    "code is correct",
)


def _extract_clean_code(value: str) -> str:
    """Extracts Python code, handling unclosed markdown fences and escaped newlines."""
    if not isinstance(value, str):
        return value

    val = value.strip()

    # Safely convert literal escaped newlines without corrupting UTF-8 characters
    if "\\n" in val and "\n" not in val:
        val = val.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "    ")

    # 1. Closed code block
    fence_match = re.search(r"```(?:python)?\s*\n?(.*?)\n?```", val, re.DOTALL)
    if fence_match:
        val = fence_match.group(1).strip()
    elif "```" in val:
        # 2. Truncated opening code block (no closing fence)
        val = re.sub(r"^.*?```(?:python)?\s*\n?", "", val, flags=re.DOTALL)
        val = re.sub(r"\n?```.*?$", "", val, flags=re.DOTALL)
        val = val.strip()

    # Clean stray trailing unescaped quotes or line continuations at EOF
    lines = val.splitlines()
    if lines and lines[-1].strip() in ("'", '"', "\\", "'''", '"""'):
        lines.pop()
        val = "\n".join(lines).strip()

    return val


def _strip_test_functions_from_patch(code: str) -> str:
    """Removes test_* functions and their decorators that bled into the patch implementation."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        lines = code.splitlines()
        non_test_lines: list[str] = []
        skipping_test = False
        for line in lines:
            if re.match(r"^\s*def\s+test_\w+", line):
                skipping_test = True
                continue
            if skipping_test:
                if line.startswith((" ", "\t")) or not line.strip():
                    continue
                skipping_test = False
            non_test_lines.append(line)
        return "\n".join(non_test_lines).strip()

    lines_to_remove: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            and hasattr(node, "lineno")
        ):
            start_lineno = node.lineno
            if node.decorator_list:
                decor_lines = [
                    d.lineno for d in node.decorator_list if hasattr(d, "lineno")
                ]
                if decor_lines:
                    start_lineno = min(decor_lines)
            end_lineno = getattr(node, "end_lineno", node.lineno)
            for line_idx in range(start_lineno, end_lineno + 1):
                lines_to_remove.add(line_idx)

    return "\n".join(
        line
        for idx, line in enumerate(code.splitlines(), start=1)
        if idx not in lines_to_remove
    ).strip()


class CodeAuditOutput(BaseModel):
    """Structured output contract the SLM must satisfy."""

    identified_bugs: list[str] = Field(
        default_factory=list,
        description="List of bugs or edge cases identified.",
    )
    suggested_patch: str = Field(
        min_length=1,
        description="Pure Python code for the source module. NEVER include test functions here.",
    )
    pytest_suite: str = Field(
        default="",
        description="Pure pytest test code starting with import pytest.",
    )

    @field_validator("suggested_patch", "pytest_suite", mode="before")
    @classmethod
    def _clean_code_field(cls, value: str) -> str:
        return _extract_clean_code(value)

    @field_validator("suggested_patch", mode="before")
    @classmethod
    def _sanitize_patch(cls, value: str) -> str:
        cleaned = value if isinstance(value, str) else _extract_clean_code(value)
        if cleaned == "PASS_UNCHANGED":
            return cleaned

        is_executable_code = False
        try:
            tree = ast.parse(cleaned)
            is_executable_code = any(
                not isinstance(stmt, ast.Expr)
                or not isinstance(stmt.value, ast.Constant)
                for stmt in tree.body
            )
        except (SyntaxError, ValueError):
            pass

        lower_val = cleaned.lower()
        if not is_executable_code and any(
            phrase in lower_val for phrase in NO_CHANGE_PHRASES
        ):
            return "PASS_UNCHANGED"

        return _strip_test_functions_from_patch(cleaned)

    @field_validator("suggested_patch")
    @classmethod
    def _verify_python_syntax(cls, value: str) -> str:
        if value == "PASS_UNCHANGED":
            return value

        # Explicit check for one-line function signature stubs
        non_empty_lines = [line.strip() for line in value.splitlines() if line.strip()]
        if len(non_empty_lines) == 1 and non_empty_lines[0].endswith(":"):
            raise ValueError(
                "suggested_patch contains only a function signature header without an indented body. "
                "You must output the entire function body."
            )

        try:
            ast.parse(value)
        except SyntaxError as exc:
            raise ValueError(f"suggested_patch is not valid Python: {exc}") from exc
        return value

    @field_validator("identified_bugs", mode="before")
    @classmethod
    def _drop_blank_bug_entries(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]


_TRIVIAL_TEST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"def\s+test_\w+\s*\([^)]*\)\s*:\s*\n\s*assert\s+True\s*$", re.MULTILINE
)


def looks_like_trivial_test_suite(pytest_suite: str) -> bool:
    """Checks if the test suite contains no tests or only trivial assertions."""
    test_functions = re.findall(r"def\s+(test_\w+)\s*\(", pytest_suite)
    if not test_functions:
        return True
    trivial_functions = _TRIVIAL_TEST_PATTERN.findall(pytest_suite)
    return len(trivial_functions) == len(test_functions)


class AgentState(TypedDict):
    source_file_path: str
    original_code: str
    current_code: str
    current_tests: str
    ast_result: ASTInspectionResult | None
    lint_result: LintRunResult | None
    sandbox_result: SandboxExecutionResult | None
    report_markdown: str
    retry_count: int
    max_retries: int
    audit_trail: list[str]
    last_error: str | None  # Tracks schema validation or verification failures


def create_initial_state(
    source_file_path: str,
    original_code: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> AgentState:
    if max_retries < 0:
        raise ValueError(f"max_retries must be non-negative, got {max_retries!r}")

    return AgentState(
        source_file_path=source_file_path,
        original_code=original_code,
        current_code=original_code,
        current_tests="",
        ast_result=None,
        lint_result=None,
        sandbox_result=None,
        report_markdown="",
        retry_count=0,
        max_retries=max_retries,
        audit_trail=[f"Audit started for {source_file_path}"],
        last_error=None,
    )
