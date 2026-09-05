"""
tests/test_state.py
=====================
Tests for `patchwork.state`. Pure data-modeling tests -- no subprocess,
no LLM, no mocking needed. `CodeAuditOutput` validation is tested
directly against the SLM failure modes it exists to guard against.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from patchwork.state import (
    DEFAULT_MAX_RETRIES,
    CodeAuditOutput,
    create_initial_state,
    looks_like_trivial_test_suite,
)


class TestCodeAuditOutputMarkdownStripping:
    def test_strips_python_fenced_patch(self) -> None:
        raw = "```python\ndef add(a, b):\n    return a + b\n```"
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch=raw,
            pytest_suite="def test_x():\n    assert True",
        )
        assert output.suggested_patch == "def add(a, b):\n    return a + b"

    def test_strips_bare_fence_no_language_tag(self) -> None:
        raw = "```\nx = 1\n```"
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch=raw,
            pytest_suite="def test_x():\n    assert True",
        )
        assert output.suggested_patch == "x = 1"

    def test_unfenced_code_passes_through_unchanged(self) -> None:
        raw = "def add(a, b):\n    return a + b"
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch=raw,
            pytest_suite="def test_x():\n    assert True",
        )
        assert output.suggested_patch == raw

    def test_fence_stripped_from_pytest_suite_field_too(self) -> None:
        raw = "```python\ndef test_add():\n    assert add(1, 2) == 3\n```"
        output = CodeAuditOutput(
            identified_bugs=[], suggested_patch="x = 1", pytest_suite=raw
        )
        assert output.pytest_suite == "def test_add():\n    assert add(1, 2) == 3"


class TestCodeAuditOutputTestContamination:
    def test_test_function_in_patch_rejected(self) -> None:
        # real failure mode observed in a live reflection run: the patch
        # field contained the fixed function AND a test_* function
        contaminated = (
            "def f():\n    return 1\n\n\ndef test_f():\n    assert f() == 1\n"
        )
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch=contaminated,
                pytest_suite="def test_x():\n    assert True",
            )

    def test_clean_patch_with_no_test_functions_accepted(self) -> None:
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def f():\n    return 1\n",
            pytest_suite="def test_f():\n    assert f() == 1\n",
        )
        assert "def test_" not in output.suggested_patch

    def test_unparseable_patch_not_falsely_flagged_as_contaminated(self) -> None:
        # syntax errors are ast_inspector's/sandbox's job to catch, not
        # this validator's -- it should not raise here
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def broken(:\n    pass",
            pytest_suite="def test_x():\n    assert True",
        )
        assert output.suggested_patch == "def broken(:\n    pass"

    def test_pytest_suite_field_itself_is_not_checked_for_test_functions(self) -> None:
        # pytest_suite is SUPPOSED to contain test_* functions -- only
        # suggested_patch is checked
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def f():\n    return 1\n",
            pytest_suite="def test_f():\n    assert f() == 1\n",
        )
        assert "def test_f" in output.pytest_suite


class TestCodeAuditOutputEmptyFieldRejection:
    def test_empty_patch_after_fence_stripping_raises(self) -> None:
        # Covers checklist item 1.4: a response that is *only* a fence
        # with nothing inside must not pass validation as if it were
        # real code.
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch="```python\n```",
                pytest_suite="def test_x():\n    assert True",
            )

    def test_whitespace_only_patch_raises(self) -> None:
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch="   \n  ",
                pytest_suite="def test_x():\n    assert True",
            )

    def test_empty_pytest_suite_raises(self) -> None:
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[], suggested_patch="x = 1", pytest_suite=""
            )


class TestCodeAuditOutputIdentifiedBugs:
    def test_empty_bug_list_is_valid(self) -> None:
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="x = 1",
            pytest_suite="def test_x():\n    assert True",
        )
        assert output.identified_bugs == []

    def test_blank_entries_filtered_out(self) -> None:
        output = CodeAuditOutput(
            identified_bugs=["off-by-one on line 4", "   ", ""],
            suggested_patch="x = 1",
            pytest_suite="def test_x():\n    assert True",
        )
        assert output.identified_bugs == ["off-by-one on line 4"]

    def test_result_is_json_serializable(self) -> None:
        output = CodeAuditOutput(
            identified_bugs=["bug"],
            suggested_patch="x = 1",
            pytest_suite="def test_x():\n    assert True",
        )
        payload = output.model_dump_json()
        assert isinstance(payload, str)
        assert '"identified_bugs":["bug"]' in payload.replace(" ", "")


class TestLooksLikeTrivialTestSuite:
    def test_single_assert_true_test_is_trivial(self) -> None:
        suite = "def test_pass():\n    assert True"
        assert looks_like_trivial_test_suite(suite) is True

    def test_real_assertion_is_not_trivial(self) -> None:
        suite = "def test_add():\n    assert add(1, 2) == 3"
        assert looks_like_trivial_test_suite(suite) is False

    def test_no_test_functions_at_all_is_trivial(self) -> None:
        assert looks_like_trivial_test_suite("x = 1\ny = 2\n") is True

    def test_mixed_suite_with_one_real_test_is_not_trivial(self) -> None:
        suite = "def test_trivial():\n    assert True\n\ndef test_real():\n    assert add(1, 2) == 3\n"
        assert looks_like_trivial_test_suite(suite) is False

    def test_multiple_trivial_tests_still_trivial(self) -> None:
        suite = "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"
        assert looks_like_trivial_test_suite(suite) is True


class TestCreateInitialState:
    def test_defaults_populated_correctly(self) -> None:
        state = create_initial_state("target.py", "def f():\n    pass\n")
        assert state["source_file_path"] == "target.py"
        assert state["original_code"] == state["current_code"]
        assert state["current_tests"] == ""
        assert state["ast_result"] is None
        assert state["lint_result"] is None
        assert state["sandbox_result"] is None
        assert state["retry_count"] == 0
        assert state["max_retries"] == DEFAULT_MAX_RETRIES
        assert len(state["audit_trail"]) == 1

    def test_custom_max_retries_respected(self) -> None:
        state = create_initial_state("target.py", "x = 1", max_retries=5)
        assert state["max_retries"] == 5

    def test_negative_max_retries_raises(self) -> None:
        with pytest.raises(ValueError):
            create_initial_state("target.py", "x = 1", max_retries=-1)

    def test_original_code_never_mutated_by_reference(self) -> None:
        source = "x = 1"
        state = create_initial_state("target.py", source)
        state["current_code"] = "x = 2"
        assert state["original_code"] == "x = 1"
        assert source == "x = 1"
