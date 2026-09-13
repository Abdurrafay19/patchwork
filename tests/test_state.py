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
    def test_test_function_in_patch_is_stripped_not_rejected(self) -> None:
        # behavior change: this used to raise ValidationError (see git
        # history), forcing the whole attempt to be discarded and burning
        # a retry. Now _strip_test_functions_from_patch repairs it inline
        # -- the real function survives, the leaked test_* function is
        # removed, and the patch is accepted. _verify_python_syntax still
        # runs afterward, so if stripping ever produced broken syntax,
        # that would still be caught and rejected -- this only covers the
        # common case where stripping succeeds cleanly.
        contaminated = (
            "def f():\n    return 1\n\n\ndef test_f():\n    assert f() == 1\n"
        )
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch=contaminated,
            pytest_suite="def test_x():\n    assert True",
        )
        assert "def test_" not in output.suggested_patch
        assert "def f():" in output.suggested_patch

    def test_clean_patch_with_no_test_functions_accepted(self) -> None:
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def f():\n    return 1\n",
            pytest_suite="def test_f():\n    assert f() == 1\n",
        )
        assert "def test_" not in output.suggested_patch

    def test_pytest_suite_field_itself_is_not_stripped_of_test_functions(self) -> None:
        # pytest_suite is SUPPOSED to contain test_* functions -- only
        # suggested_patch goes through _strip_test_functions_from_patch
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def f():\n    return 1\n",
            pytest_suite="def test_f():\n    assert f() == 1\n",
        )
        assert "def test_f" in output.pytest_suite

    def test_stripping_a_syntactically_broken_patch_does_not_crash(self) -> None:
        # _strip_test_functions_from_patch's own ast.parse can fail on
        # code that's simultaneously contaminated AND malformed -- it
        # must return the code unchanged rather than raising, leaving
        # _verify_python_syntax (which runs after) to correctly reject it
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch="def broken(:\n    def test_x(:\n    pass",
                pytest_suite="def test_x():\n    assert True",
            )


class TestCodeAuditOutputSyntaxValidation:
    def test_unparseable_patch_is_rejected(self) -> None:
        # covers _verify_python_syntax directly: a patch that isn't
        # valid Python must fail schema validation here, not silently
        # pass through and only surface as a confusing sandbox failure
        # three steps downstream (see manual CLI run against
        # manual_smoke_test.py, which is what surfaced this gap -- the
        # SLM returned a plain-English sentence instead of code, and it
        # sailed through every check that existed at the time).
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch="def broken(:\n    pass",
                pytest_suite="def test_x():\n    assert True",
            )

    def test_prose_instead_of_code_is_rejected(self) -> None:
        # the exact real-world failure that motivated this validator --
        # a syntactically-nonsensical English sentence is technically
        # non-empty text, so only an actual parse attempt catches it
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch=(
                    "Replace the '+' operator with the '/' operator "
                    "in the buggy source code."
                ),
                pytest_suite="def test_x():\n    assert True",
            )

    def test_valid_python_patch_still_accepted(self) -> None:
        # sanity check that the new validator doesn't over-reject --
        # ordinary valid code must still pass cleanly
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def f():\n    return 1\n",
            pytest_suite="def test_f():\n    assert f() == 1\n",
        )
        assert output.suggested_patch == "def f():\n    return 1"

    def test_one_line_signature_stub_is_rejected(self) -> None:
        # new validator: a patch that's only a function header with no
        # indented body (e.g. "def f():") is syntactically valid Python
        # on its own only if it has *some* body, so this specifically
        # catches the "signature with nothing after it" truncation case
        with pytest.raises(ValidationError):
            CodeAuditOutput(
                identified_bugs=[],
                suggested_patch="def f():",
                pytest_suite="def test_f():\n    assert True",
            )

    def test_pass_unchanged_sentinel_bypasses_syntax_check(self) -> None:
        # new "no changes needed" pathway: if the model's raw output
        # contains one of NO_CHANGE_PHRASES, _sanitize_patch rewrites
        # suggested_patch to the literal sentinel "PASS_UNCHANGED" before
        # _verify_python_syntax ever runs -- that sentinel is obviously
        # not valid Python on its own, so the syntax check must special-
        # case and allow it through rather than rejecting it
        output = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="The code is correct and needs no changes.",
            pytest_suite="def test_f():\n    assert True",
        )
        assert output.suggested_patch == "PASS_UNCHANGED"


class TestCodeAuditOutputEmptyFieldRejection:
    def test_empty_patch_after_fence_stripping_raises(self) -> None:
        # Covers checklist item 1.4: a response that is *only* a fence
        # with nothing inside must not pass validation as if it were
        # real code. suggested_patch still enforces min_length=1 --
        # only pytest_suite's constraint was relaxed (see the
        # TestCodeAuditOutputOptionalTestSuite class below).
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


class TestCodeAuditOutputOptionalTestSuite:
    def test_empty_pytest_suite_is_now_accepted(self) -> None:
        # behavior change: pytest_suite lost its min_length=1 constraint
        # and now defaults to "". An empty suite is a legitimate "no
        # tests provided" outcome (e.g. paired with the PASS_UNCHANGED
        # patch sentinel), which graph.py's node_execute_tests handles
        # by skipping sandbox execution rather than running against an
        # empty suite -- see test_graph.py's
        # test_blank_tests_are_skipped_not_executed for that side.
        output = CodeAuditOutput(
            identified_bugs=[], suggested_patch="x = 1", pytest_suite=""
        )
        assert output.pytest_suite == ""

    def test_pytest_suite_field_omitted_entirely_defaults_to_empty(self) -> None:
        output = CodeAuditOutput(identified_bugs=[], suggested_patch="x = 1")
        assert output.pytest_suite == ""


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
        assert state["report_markdown"] == ""
        assert state["retry_count"] == 0
        assert state["max_retries"] == DEFAULT_MAX_RETRIES
        assert state["last_error"] is None
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
