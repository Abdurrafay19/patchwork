"""
patchwork.state
=================
Shared type contracts for the Patchwork agent: the Pydantic schema the
SLM's structured output must conform to, and the LangGraph `AgentState`
that flows between nodes.

This module has no LLM calls and no subprocess calls -- it's pure data
modeling, which is why it's built before `graph.py`. Per
`critical_engineering_and_execution_advice`, LangGraph nodes must treat
state as immutable (return a new dict with updated keys, never mutate
the input dict in place); this module only defines the *shape* of that
state, it does not enforce immutability itself -- that discipline lives
in the node implementations in `graph.py`.
"""

from __future__ import annotations

import ast
import re
from typing import Final, TypedDict

from pydantic import BaseModel, Field, field_validator

from patchwork.tools.ast_inspector import ASTInspectionResult
from patchwork.tools.linter import LintRunResult
from patchwork.tools.sandbox import SandboxExecutionResult

DEFAULT_MAX_RETRIES: Final[int] = 3

_MARKDOWN_FENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*```(?:python)?\s*\n?(.*?)\n?```\s*$", re.DOTALL
)

# Checklist item 4.2 ("Trivial Test Suites"): a generated suite whose only
# assertion is a tautology. Not exhaustive -- a suite could be trivial in
# other ways -- but this catches the specific pattern the checklist calls
# out, which is the one an SLM under context pressure actually produces.
_TRIVIAL_TEST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"def\s+test_\w+\s*\([^)]*\)\s*:\s*\n\s*assert\s+True\s*$", re.MULTILINE
)


def _strip_markdown_fences(value: str) -> str:
    """Strips a single wrapping ```/```python markdown code fence.

    Addresses checklist item 1.4 ("Markdown Contamination"): SLMs
    frequently wrap structured-output string fields in code fences even
    when explicitly instructed to return raw code, which would otherwise
    corrupt the patch/test content with non-Python fence lines.

    Args:
        value: The raw string as returned by the SLM.

    Returns:
        The value with a single wrapping fence removed, if present.
        Text that isn't fenced is returned unchanged. Only strips one
        wrapping fence -- it does not attempt to repair fences embedded
        mid-string.
    """
    match = _MARKDOWN_FENCE_PATTERN.match(value)
    if match:
        return match.group(1)
    return value


def _contains_test_function(code: str) -> bool:
    # detects checklist-adjacent contamination: SLM bleeding test functions
    # into suggested_patch instead of keeping them in pytest_suite. Uses
    # ast, not regex, since a substring match on "def test_" would also
    # false-positive on a docstring or comment mentioning test functions.
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False  # not this check's job to catch syntax errors

    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


class CodeAuditOutput(BaseModel):
    """Structured output contract the SLM must satisfy for a single
    audit-and-generate or reflect-and-heal turn.

    Attributes:
        identified_bugs: Human-readable list of bugs, logic errors, or
            missing edge cases the SLM found. May be empty for code the
            SLM judges to have no issues -- an empty list is a valid
            audit result, not a schema violation.
        suggested_patch: Complete revised Python source for the target
            file. Markdown fences are stripped automatically; the field
            must be non-empty after stripping.
        pytest_suite: Complete pytest test suite covering the identified
            edge cases. Markdown fences are stripped automatically; the
            field must be non-empty after stripping.
    """

    identified_bugs: list[str] = Field(default_factory=list)
    suggested_patch: str = Field(min_length=1)
    pytest_suite: str = Field(min_length=1)

    @field_validator("suggested_patch", "pytest_suite", mode="before")
    @classmethod
    def _clean_code_field(cls, value: str) -> str:
        """Strips markdown fences and surrounding whitespace before the
        `min_length=1` constraint is checked, so a fenced-but-otherwise-
        empty response (```` ```python\\n``` ````) correctly fails
        validation instead of passing with fence characters as content.
        """
        if not isinstance(value, str):
            return value
        return _strip_markdown_fences(value).strip()

    @field_validator("suggested_patch")
    @classmethod
    def _reject_test_contaminated_patch(cls, value: str) -> str:
        # real bug caught via manual_reflection_test.py: a reflection
        # attempt returned test_* functions inside suggested_patch, mixed
        # with the actual source. Rejecting here routes it through the
        # same schema-validation-failure path graph.py already handles
        # (burn a retry, don't corrupt current_code) instead of letting
        # contaminated code silently become the new "fixed" file.
        if _contains_test_function(value):
            raise ValueError(
                "suggested_patch contains test_* function(s) -- test code bled into the source patch"
            )
        return value

    @field_validator("identified_bugs", mode="before")
    @classmethod
    def _drop_blank_bug_entries(cls, value: object) -> object:
        """Filters out whitespace-only entries the SLM sometimes emits
        as list padding, without rejecting a genuinely empty list."""
        if not isinstance(value, list):
            return value
        return [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]


def looks_like_trivial_test_suite(pytest_suite: str) -> bool:
    """Flags the specific trivial-test pattern from checklist item 4.2:
    a test function whose entire body is `assert True`.

    This is a heuristic for the reflect/route logic to consult, not a
    validator on `CodeAuditOutput` -- rejecting outright at the schema
    level would also reject a legitimately trivial-but-intentional smoke
    test, which isn't this module's call to make.

    Args:
        pytest_suite: The full pytest suite source to inspect.

    Returns:
        True if every `test_*` function in the suite matches the
        `assert True`-only body pattern. A suite with zero test
        functions is also considered trivial (nothing is actually being
        verified).
    """
    test_functions = re.findall(r"def\s+(test_\w+)\s*\(", pytest_suite)
    if not test_functions:
        return True
    trivial_functions = _TRIVIAL_TEST_PATTERN.findall(pytest_suite)
    return len(trivial_functions) == len(test_functions)


class AgentState(TypedDict):
    """LangGraph state passed between nodes in the Patchwork audit graph.

    Deliberately embeds the strictly-typed result models from
    `patchwork.tools` (`ASTInspectionResult`, `LintRunResult`,
    `SandboxExecutionResult`) rather than flattening their fields into
    loose strings/dicts here -- the tools already define the correct
    shape for their own output, and duplicating that shape in a second
    place would just create a second thing to keep in sync.

    Attributes:
        source_file_path: Path to the original file the user submitted.
        original_code: The unmodified source, kept for diffing and for
            the final report -- never overwritten during the run.
        current_code: The latest patched version of the source. This is
            what gets linted, tested, and (on failure) re-patched.
        current_tests: The latest generated pytest suite.
        ast_result: Most recent AST inspection of `current_code`, or
            `None` before the first analysis pass has run.
        lint_result: Most recent lint run against `current_code`, or
            `None` before the first analysis pass has run.
        sandbox_result: Most recent sandboxed test execution, or `None`
            before the first execute pass has run.
        retry_count: Number of reflect-and-heal cycles completed so far.
        max_retries: Hard ceiling on `retry_count` before the graph
            routes to a terminal "fail gracefully" edge instead of
            looping again.
        audit_trail: Ordered, human-readable log of what happened at
            each node, for the final Markdown report -- append-only.
    """

    source_file_path: str
    original_code: str
    current_code: str
    current_tests: str
    ast_result: ASTInspectionResult | None
    lint_result: LintRunResult | None
    sandbox_result: SandboxExecutionResult | None
    retry_count: int
    max_retries: int
    audit_trail: list[str]


def create_initial_state(
    source_file_path: str,
    original_code: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> AgentState:
    """Builds the starting `AgentState` for a fresh audit run.

    Centralizing construction here means every entry point (CLI,
    benchmark harness, future API) produces a state with identical
    defaults, rather than each caller hand-assembling the dict and
    risking a missing or misspelled key that `TypedDict` won't catch
    at runtime.

    Args:
        source_file_path: Path to the file being audited, for the audit
            trail and final report. Not read by this function -- the
            caller is responsible for having already loaded `original_code`.
        original_code: The full, unmodified source of the target file.
        max_retries: Reflect-and-heal retry ceiling for this run. Must be
            non-negative.

    Returns:
        A fresh `AgentState` with `current_code` seeded from
        `original_code`, no tests generated yet, zero retries used, and
        an audit trail containing a single "run started" entry.

    Raises:
        ValueError: If `max_retries` is negative.
    """
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
        retry_count=0,
        max_retries=max_retries,
        audit_trail=[f"Audit started for {source_file_path}"],
    )