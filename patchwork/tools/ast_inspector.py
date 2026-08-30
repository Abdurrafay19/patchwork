"""
Deterministic AST-based structural inspection for the Patchwork self-healing code-audit engine.

this tool never shells out to a subprocess -- `ast.parse` only builds a syntax tree, it does not execute
any code, so it's safe to run in-process directly against SLM-authored
source. Its job is narrow: confirm the code is even syntactically valid
Python before anything downstream (ruff, pytest) wastes a cycle on it,
and extract a lightweight structural inventory (functions, classes,
docstring coverage) that's cheap to hand to the SLM as context.

"""

from __future__ import annotations

import ast
import logging
from typing import Final

from pydantic import BaseModel, Field

logger = logging.getLogger("patchwork.tools.ast_inspector")

MAX_ERROR_MESSAGE_CHARS: Final[int] = 300


class FunctionInfo(BaseModel):
    """Structural summary of a single function or method definition."""

    name: str
    line: int
    arg_count: int
    has_docstring: bool
    is_async: bool


class ClassInfo(BaseModel):
    """Structural summary of a single class definition."""

    name: str
    line: int
    method_count: int
    has_docstring: bool


class ASTInspectionResult(BaseModel):
    """Strictly-typed result of inspecting one source file's AST.

    Attributes:
        syntax_valid: False if `ast.parse` raised `SyntaxError`. When
            False, `functions`/`classes` are empty and
            `syntax_error_message`/`syntax_error_line` are populated
            instead -- there is no partial tree to report on.
        functions: Top-level and nested function/method definitions,
            in the order they appear in source.
        classes: Top-level class definitions, in the order they appear.
        total_lines: Number of lines in the source, via `splitlines()`.
        syntax_error_message: Human-readable parse error, truncated.
        syntax_error_line: 1-indexed line the parser failed on, if known.
        syntax_error_column: 1-indexed column the parser failed on.
    """

    syntax_valid: bool
    functions: list[FunctionInfo] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    total_lines: int = 0
    syntax_error_message: str | None = None
    syntax_error_line: int | None = None
    syntax_error_column: int | None = None


def _has_leading_docstring(body: list[ast.stmt]) -> bool:
    """Checks whether a function/class body opens with a docstring.

    Args:
        body: The `.body` list of an `ast.FunctionDef`, `ast.AsyncFunctionDef`,
            or `ast.ClassDef` node.

    Returns:
        True if the first statement is a bare string-literal expression.
    """
    if not body:
        return False
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


def _extract_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> FunctionInfo:
    """Builds a `FunctionInfo` from a function/async-function AST node.

    Args:
        node: The function definition node to summarize.

    Returns:
        A populated `FunctionInfo`.
    """
    args = node.args
    arg_count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    return FunctionInfo(
        name=node.name,
        line=node.lineno,
        arg_count=arg_count,
        has_docstring=_has_leading_docstring(node.body),
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _extract_class_info(node: ast.ClassDef) -> ClassInfo:
    """Builds a `ClassInfo` from a class-definition AST node.

    Args:
        node: The class definition node to summarize.

    Returns:
        A populated `ClassInfo`. `method_count` only counts direct
        children of the class body, not methods of nested classes.
    """
    method_count = sum(
        1
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return ClassInfo(
        name=node.name,
        line=node.lineno,
        method_count=method_count,
        has_docstring=_has_leading_docstring(node.body),
    )


def inspect_source(source_code: str) -> ASTInspectionResult:
    """Parses Python source into an AST and extracts a structural summary.

    This function never raises for malformed *Python* input -- syntax
    errors, null-byte source, and excessively deep nesting are all
    caught and represented as data on the returned model. It only raises
    for programming errors on the caller's side (e.g. passing a
    non-`str`), which `mypy --strict` should catch before runtime anyway.

    Args:
        source_code: The full contents of the module to inspect.

    Returns:
        An `ASTInspectionResult` describing either the extracted
        structure (if the source parsed successfully) or the parse
        failure (if it did not).
    """
    total_lines = len(source_code.splitlines())

    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        logger.warning(
            "ast_parse_syntax_error",
            extra={
                "event": "ast_parse_syntax_error",
                "line": exc.lineno,
                "detail": str(exc.msg),
            },
        )
        message = str(exc.msg) or "Unknown syntax error"
        if len(message) > MAX_ERROR_MESSAGE_CHARS:
            message = f"{message[:MAX_ERROR_MESSAGE_CHARS]}...[truncated]"
        return ASTInspectionResult(
            syntax_valid=False,
            total_lines=total_lines,
            syntax_error_message=message,
            syntax_error_line=exc.lineno,
            syntax_error_column=exc.offset,
        )
    except ValueError as exc:
        # ast.parse raises plain ValueError (not SyntaxError) for source
        # containing null bytes.
        logger.warning(
            "ast_parse_value_error",
            extra={"event": "ast_parse_value_error", "error": str(exc)},
        )
        return ASTInspectionResult(
            syntax_valid=False,
            total_lines=total_lines,
            syntax_error_message=f"Invalid source: {exc}",
        )
    except RecursionError:
        # Pathologically deep nesting can exceed Python's own recursion
        # limit while ast.parse builds or walks the tree.
        logger.error(
            "ast_parse_recursion_error",
            extra={"event": "ast_parse_recursion_error", "total_lines": total_lines},
        )
        return ASTInspectionResult(
            syntax_valid=False,
            total_lines=total_lines,
            syntax_error_message="Source is too deeply nested to parse safely.",
        )

    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_extract_function_info(node))
        elif isinstance(node, ast.ClassDef):
            classes.append(_extract_class_info(node))

    logger.info(
        "ast_inspect_complete",
        extra={
            "event": "ast_inspect_complete",
            "function_count": len(functions),
            "class_count": len(classes),
            "total_lines": total_lines,
        },
    )
    return ASTInspectionResult(
        syntax_valid=True,
        functions=functions,
        classes=classes,
        total_lines=total_lines,
    )
