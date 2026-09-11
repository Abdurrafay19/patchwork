"""
benchmarks.evaluate
=====================
Runs the full agent graph against every defect in the dataset and grades
the result against that defect's oracle test -- never against the SLM's
own self-written test suite, since a model that writes weak tests would
otherwise score as "fixed" even when it isn't.

structured_llm is injected, same pattern as graph.py, so tests can mock
it and never touch a real Ollama server. The real run (main()) uses the
actual model.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Final

from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from benchmarks.manifest import (
    DefectRecord,
    load_defect_source,
    load_manifest,
    load_oracle_test,
)
from patchwork.graph import build_patchwork_graph, build_structured_llm
from patchwork.state import CodeAuditOutput, create_initial_state
from patchwork.telemetry.profiler import profile_call
from patchwork.tools.sandbox import run_pytest_sandbox

logger = logging.getLogger("benchmarks.evaluate")

RESULTS_PATH: Final[Path] = Path(__file__).parent / "results.json"
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_ORACLE_TIMEOUT_SEC: Final[int] = 15


class DefectResult(BaseModel):
    defect_id: str
    category: str
    passed_oracle: bool  # the real grade -- did the fix actually work
    passed_own_tests: bool  # informational only -- the SLM grading itself
    retry_count: int
    max_retries: int
    duration_sec: float = Field(ge=0.0)
    peak_vram_mb: float | None = None
    gpu_available: bool = False
    error: str | None = None  # populated only if the run itself crashed


class EvaluationSummary(BaseModel):
    total_defects: int
    pass_at_1: int  # passed_oracle True with retry_count == 0
    pass_at_1_rate: float
    pass_overall: int  # passed_oracle True at any retry_count <= max_retries
    pass_overall_rate: float
    avg_duration_sec: float
    avg_peak_vram_mb: float | None
    results: list[DefectResult] = Field(default_factory=list)


def _grade_against_oracle(record: DefectRecord, final_code: str) -> bool:
    oracle = load_oracle_test(record)
    result = run_pytest_sandbox(
        final_code, oracle, timeout_sec=DEFAULT_ORACLE_TIMEOUT_SEC
    )
    return result.passed


def evaluate_defect(
    record: DefectRecord,
    structured_llm: Runnable[str, CodeAuditOutput],
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> DefectResult:
    source = load_defect_source(record)
    graph = build_patchwork_graph(structured_llm)
    initial = create_initial_state(
        record.source_filename, source, max_retries=max_retries
    )

    try:
        final_state, telemetry = profile_call(graph.invoke, initial)
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        # crash-isolation boundary for the batch harness: an unexpected
        # transport/runtime failure on one defect must not kill the rest
        # of a 25-defect run. graph.py already handles the SLM schema
        # failures internally -- this only catches what escapes that.
        logger.error(
            "defect_evaluation_crashed",
            extra={
                "event": "defect_evaluation_crashed",
                "defect_id": record.id,
                "error": str(exc),
            },
        )
        return DefectResult(
            defect_id=record.id,
            category=record.category,
            passed_oracle=False,
            passed_own_tests=False,
            retry_count=0,
            max_retries=max_retries,
            duration_sec=0.0,
            error=str(exc),
        )

    sandbox_result = final_state["sandbox_result"]
    passed_own_tests = sandbox_result.passed if sandbox_result else False
    passed_oracle = _grade_against_oracle(record, final_state["current_code"])

    return DefectResult(
        defect_id=record.id,
        category=record.category,
        passed_oracle=passed_oracle,
        passed_own_tests=passed_own_tests,
        retry_count=final_state["retry_count"],
        max_retries=max_retries,
        duration_sec=telemetry.duration_sec,
        peak_vram_mb=telemetry.peak_vram_mb,
        gpu_available=telemetry.gpu_available,
    )


def evaluate_all(
    structured_llm: Runnable[str, CodeAuditOutput],
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> EvaluationSummary:
    manifest = load_manifest()
    results: list[DefectResult] = []

    for record in manifest.defects:
        logger.info(
            "evaluating_defect",
            extra={"event": "evaluating_defect", "defect_id": record.id},
        )
        result = evaluate_defect(record, structured_llm, max_retries)
        results.append(result)

    total = len(results)
    pass_at_1 = sum(1 for r in results if r.passed_oracle and r.retry_count == 0)
    pass_overall = sum(1 for r in results if r.passed_oracle)
    durations = [r.duration_sec for r in results]
    vram_values = [r.peak_vram_mb for r in results if r.peak_vram_mb is not None]

    return EvaluationSummary(
        total_defects=total,
        pass_at_1=pass_at_1,
        pass_at_1_rate=pass_at_1 / total if total else 0.0,
        pass_overall=pass_overall,
        pass_overall_rate=pass_overall / total if total else 0.0,
        avg_duration_sec=sum(durations) / total if total else 0.0,
        avg_peak_vram_mb=(sum(vram_values) / len(vram_values)) if vram_values else None,
        results=results,
    )


def save_results(summary: EvaluationSummary, path: Path = RESULTS_PATH) -> None:
    path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")


def _print_summary(summary: EvaluationSummary) -> None:
    print(f"\n{'=' * 60}")
    print(f"Total defects:     {summary.total_defects}")
    print(
        f"Pass@1:            {summary.pass_at_1}/{summary.total_defects} ({summary.pass_at_1_rate:.0%})"
    )
    print(
        f"Pass (overall):    {summary.pass_overall}/{summary.total_defects} ({summary.pass_overall_rate:.0%})"
    )
    print(f"Avg duration:      {summary.avg_duration_sec:.2f}s")
    vram_line = (
        f"{summary.avg_peak_vram_mb:.0f}MB"
        if summary.avg_peak_vram_mb
        else "N/A (no GPU)"
    )
    print(f"Avg peak VRAM:     {vram_line}")
    print(f"{'=' * 60}\n")

    for result in summary.results:
        status = "PASS" if result.passed_oracle else "FAIL"
        note = f" -- CRASHED: {result.error}" if result.error else ""
        print(
            f"  [{status}] {result.defect_id:28} retries={result.retry_count}/{result.max_retries}{note}"
        )


def main() -> None:
    print("Building structured LLM client...")
    structured_llm = build_structured_llm()

    print("Running 25-defect benchmark. This will take a while on a 3B model...\n")
    start = time.perf_counter()
    summary = evaluate_all(structured_llm)
    elapsed = time.perf_counter() - start

    _print_summary(summary)
    print(f"Total wall time: {elapsed:.1f}s")

    save_results(summary)
    print(f"Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
