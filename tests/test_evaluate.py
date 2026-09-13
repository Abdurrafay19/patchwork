"""
tests/test_evaluate.py
=========================
All tests mock structured_llm -- never touch real Ollama. But grading
runs the REAL dataset, REAL oracle tests, and REAL sandbox execution,
since this module's entire job is correctly wiring those together.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from benchmarks.evaluate import EvaluationSummary, evaluate_all, evaluate_defect
from benchmarks.manifest import DefectRecord, load_manifest
from patchwork.state import CodeAuditOutput


def _record(defect_id: str) -> DefectRecord:
    manifest = load_manifest()
    return next(r for r in manifest.defects if r.id == defect_id)


class TestEvaluateDefect:
    def test_correct_fix_passes_oracle(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = CodeAuditOutput(
            identified_bugs=["fixed"],
            suggested_patch=(
                "def append_item(item, target_list=None):\n"
                "    if target_list is None:\n"
                "        target_list = []\n"
                "    target_list.append(item)\n"
                "    return target_list\n"
            ),
            pytest_suite="def test_x():\n    assert True\n",
        )
        result = evaluate_defect(_record("mutable_default_01"), mock_llm, max_retries=0)
        assert result.passed_oracle is True
        assert result.error is None

    def test_wrong_fix_fails_oracle(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch="def placeholder():\n    pass\n",
            pytest_suite="def test_x():\n    assert True\n",
        )
        result = evaluate_defect(_record("mutable_default_01"), mock_llm, max_retries=0)
        assert result.passed_oracle is False

    def test_grading_uses_oracle_not_slms_own_tests(self) -> None:
        # SLM writes a trivial/wrong self-test that would pass against
        # its own broken patch -- passed_own_tests may be True, but
        # passed_oracle must still correctly be False
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = CodeAuditOutput(
            identified_bugs=[],
            suggested_patch=(
                "def append_item(item, target_list=[]):\n"
                "    target_list.append(item)\n"
                "    return target_list\n"
            ),  # unfixed
            pytest_suite="def test_trivial():\n    assert True\n",  # passes regardless
        )
        result = evaluate_defect(_record("mutable_default_01"), mock_llm, max_retries=0)
        assert result.passed_own_tests is True  # trivial test passes
        assert result.passed_oracle is False  # but the real bug is still there

    def test_transport_failure_does_not_crash_evaluation(self) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = ConnectionError("ollama unreachable")
        result = evaluate_defect(_record("mutable_default_01"), mock_llm, max_retries=0)
        assert result.passed_oracle is False
        assert result.error is not None


@pytest.fixture(scope="module")
def summary() -> EvaluationSummary:
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = CodeAuditOutput(
        identified_bugs=[],
        suggested_patch="x = 1\n",
        pytest_suite="def test_x():\n    assert True\n",
    )
    return evaluate_all(mock_llm, max_retries=0)


class TestEvaluateAll:
    def test_runs_all_defects_in_manifest(self, summary: EvaluationSummary) -> None:
        assert summary.total_defects == 100
        assert len(summary.results) == 100

    def test_pass_at_1_counts_only_zero_retry_passes(
        self, summary: EvaluationSummary
    ) -> None:
        assert summary.pass_at_1 == 0
        assert summary.pass_at_1_rate == 0.0

    def test_rates_are_fractions_of_total(self, summary: EvaluationSummary) -> None:
        assert summary.pass_overall_rate == summary.pass_overall / summary.total_defects
