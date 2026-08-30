"""
Tests for `patchwork.tools.ast_inspector`. No subprocess mocking needed
here -- `inspect_source` is pure, in-process, and deterministic, so
every test exercises the real function directly.
"""

from __future__ import annotations

from patchwork.tools.ast_inspector import (
    ASTInspectionResult,
    inspect_source,
)


class TestInspectSourceValidCode:
    def test_simple_function_detected(self) -> None:
        source = "def add(a, b):\n    return a + b\n"
        result = inspect_source(source)
        assert result.syntax_valid is True
        assert len(result.functions) == 1
        assert result.functions[0].name == "add"
        assert result.functions[0].arg_count == 2
        assert result.functions[0].has_docstring is False

    def test_function_with_docstring_detected(self) -> None:
        source = 'def add(a, b):\n    """Adds two numbers."""\n    return a + b\n'
        result = inspect_source(source)
        assert result.functions[0].has_docstring is True

    def test_async_function_flagged(self) -> None:
        source = "async def fetch():\n    pass\n"
        result = inspect_source(source)
        assert result.functions[0].is_async is True

    def test_class_with_methods_detected(self) -> None:
        source = (
            "class Widget:\n"
            '    """A widget."""\n'
            "    def spin(self):\n"
            "        pass\n"
            "    def stop(self):\n"
            "        pass\n"
        )
        result = inspect_source(source)
        assert len(result.classes) == 1
        assert result.classes[0].name == "Widget"
        assert result.classes[0].method_count == 2
        assert result.classes[0].has_docstring is True
        # methods are still individually reported in `functions` too
        assert len(result.functions) == 2

    def test_class_without_docstring(self) -> None:
        source = "class Empty:\n    pass\n"
        result = inspect_source(source)
        assert result.classes[0].has_docstring is False
        assert result.classes[0].method_count == 0

    def test_nested_function_still_found(self) -> None:
        source = "def outer():\n    def inner():\n        pass\n    return inner\n"
        result = inspect_source(source)
        names = {f.name for f in result.functions}
        assert names == {"outer", "inner"}

    def test_total_lines_counted(self) -> None:
        source = "x = 1\ny = 2\nz = 3\n"
        result = inspect_source(source)
        assert result.total_lines == 3

    def test_empty_source_is_valid_with_no_definitions(self) -> None:
        result = inspect_source("")
        assert result.syntax_valid is True
        assert result.functions == []
        assert result.classes == []

    def test_arg_count_includes_posonly_and_kwonly(self) -> None:
        source = "def f(a, b, /, c, *, d):\n    pass\n"
        result = inspect_source(source)
        # a, b (posonly) + c (regular) + d (kwonly) = 4; *args/**kwargs excluded by design
        assert result.functions[0].arg_count == 4


class TestInspectSourceInvalidCode:
    def test_syntax_error_reported_not_raised(self) -> None:
        source = "def broken(:\n    pass\n"
        result = inspect_source(source)
        assert isinstance(result, ASTInspectionResult)
        assert result.syntax_valid is False
        assert result.functions == []
        assert result.classes == []
        assert result.syntax_error_message is not None
        assert result.syntax_error_line == 1

    def test_unclosed_bracket_reported(self) -> None:
        source = "x = [1, 2, 3\n"
        result = inspect_source(source)
        assert result.syntax_valid is False
        assert result.syntax_error_line is not None

    def test_null_byte_source_reported_not_raised(self) -> None:
        source = "x = 1\x00\n"
        result = inspect_source(source)
        assert result.syntax_valid is False
        assert result.syntax_error_message is not None

    def test_total_lines_still_counted_on_syntax_error(self) -> None:
        source = "x = 1\ny = 2\ndef broken(:\n    pass\n"
        result = inspect_source(source)
        assert result.syntax_valid is False
        assert result.total_lines == 4


class TestInspectSourceResultShape:
    def test_result_is_pydantic_model_and_json_serializable(self) -> None:
        result = inspect_source("def f():\n    pass\n")
        payload = result.model_dump_json()
        assert isinstance(payload, str)
        assert '"syntax_valid":true' in payload.replace(" ", "")

    def test_invalid_result_is_also_json_serializable(self) -> None:
        result = inspect_source("def broken(:\n")
        payload = result.model_dump_json()
        assert '"syntax_valid":false' in payload.replace(" ", "")
