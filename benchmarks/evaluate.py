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

Streams each defect's graph run via graph.stream(stream_mode="values")
instead of a single blocking graph.invoke() -- on a slow local 3B model,
a 100-defect run can take tens of minutes with total silence otherwise,
which is indistinguishable from a hang. Per-node progress (via rich) and
a rough tokens/sec estimate give a live signal that something is still
happening and roughly how fast.
"""

from __future__ import annotations

import logging
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Final, cast

from langchain_core.runnables import Runnable
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from benchmarks.manifest import (
    DefectRecord,
    load_defect_source,
    load_manifest,
    load_oracle_test,
)
from patchwork.graph import (
    DEFAULT_LLM_TIMEOUT_SEC,
    DEFAULT_MODEL,
    build_patchwork_graph,
    build_structured_llm,
)
from patchwork.state import AgentState, CodeAuditOutput, create_initial_state
from patchwork.telemetry.profiler import profile_call
from patchwork.tools.sandbox import run_pytest_sandbox

logger = logging.getLogger("benchmarks.evaluate")

RESULTS_PATH: Final[Path] = Path(__file__).parent / "results.json"
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_ORACLE_TIMEOUT_SEC: Final[int] = 15

# rough chars-per-token heuristic for the tok/s estimate -- structured
# output goes through with_structured_output(), which does not reliably
# surface Ollama's native eval_count/eval_duration metadata through
# LangChain, so an exact count isn't available without deeper surgery
# on how graph.py invokes the model. This is a directional signal
# ("is generation still moving, roughly how fast"), not a precise metric.
_CHARS_PER_TOKEN_ESTIMATE: Final[float] = 4.0

_GENERATION_TRAIL_MARKERS: Final[tuple[str, ...]] = (
    "Generated patch",
    "Reflection attempt",
)


class AttemptRecord(BaseModel):
    attempt: int
    patch_code: str
    test_code: str
    passed_own_tests: bool | None = None
    passed_oracle: bool | None = None


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
    attempts: list[AttemptRecord] = Field(default_factory=list)


class EvaluationSummary(BaseModel):
    model: str = DEFAULT_MODEL
    total_defects: int
    pass_at_1: int  # passed oracle with retry_count == 0 (empirical lower bound)
    pass_at_1_rate: float
    pass_overall: int  # passed oracle at any retry_count <= max_retries
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


def _run_graph_with_progress(
    graph: CompiledStateGraph[Any, Any, Any, Any],
    initial: AgentState,
    console: Console,
) -> tuple[AgentState, list[AttemptRecord]]:
    """Streams the graph node-by-node, printing progress and a rough
    tokens/sec estimate for generation/reflection steps.

    Args:
        graph: A compiled patchwork graph.
        initial: The starting AgentState for this defect.
        console: Shared rich Console to print progress lines to.

    Returns:
        The final AgentState and list of recorded attempts.
    """
    final_state: AgentState = initial
    prev_time = time.perf_counter()
    prev_content_len = len(initial["current_code"]) + len(initial["current_tests"])
    attempts: list[AttemptRecord] = []
    seen_retries: set[int] = set()

    for state in graph.stream(initial, stream_mode="values"):
        now = time.perf_counter()
        step_duration = now - prev_time
        entry = state["audit_trail"][-1]
        content_len = len(state["current_code"]) + len(state["current_tests"])

        if "Test execution:" in entry:
            retry = state["retry_count"]
            if retry not in seen_retries:
                seen_retries.add(retry)
                passed = (
                    state["sandbox_result"].passed if state["sandbox_result"] else None
                )
                attempts.append(
                    AttemptRecord(
                        attempt=retry,
                        patch_code=state["current_code"],
                        test_code=state["current_tests"],
                        passed_own_tests=passed,
                    )
                )

        tok_s_note = ""
        is_generation_step = any(
            marker in entry for marker in _GENERATION_TRAIL_MARKERS
        )
        if is_generation_step and step_duration > 0:
            delta_chars = abs(content_len - prev_content_len)
            approx_tokens = delta_chars / _CHARS_PER_TOKEN_ESTIMATE
            approx_tok_s = approx_tokens / step_duration
            tok_s_note = (
                f" [dim](~{approx_tok_s:.1f} tok/s est., {step_duration:.1f}s)[/dim]"
            )
        elif step_duration > 0:
            tok_s_note = f" [dim]({step_duration:.1f}s)[/dim]"

        console.print(f"    [dim]->[/dim] {entry}{tok_s_note}")

        prev_time = now
        prev_content_len = content_len
        final_state = cast(AgentState, state)

    if not attempts and final_state["current_tests"]:
        sandbox = final_state["sandbox_result"]
        attempts.append(
            AttemptRecord(
                attempt=final_state["retry_count"],
                patch_code=final_state["current_code"],
                test_code=final_state["current_tests"],
                passed_own_tests=sandbox.passed if sandbox else None,
            )
        )

    return final_state, attempts


def evaluate_defect(
    record: DefectRecord,
    structured_llm: Runnable[str, CodeAuditOutput],
    max_retries: int = DEFAULT_MAX_RETRIES,
    defect_index: int = 1,
    total_defects: int = 1,
    console: Console | None = None,
) -> DefectResult:
    if console is None:
        console = Console()

    source = load_defect_source(record)
    graph = build_patchwork_graph(structured_llm)
    initial = create_initial_state(
        record.source_filename, source, max_retries=max_retries
    )

    console.rule(f"[bold]\\[{defect_index}/{total_defects}] {record.id}[/bold]")

    try:
        (final_state, attempts), telemetry = profile_call(
            _run_graph_with_progress, graph, initial, console
        )
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        # Crash-isolation boundary: an unexpected transport or runtime failure
        # on one defect must not abort the remaining benchmark run.
        logger.error(
            "defect_evaluation_crashed",
            extra={
                "event": "defect_evaluation_crashed",
                "defect_id": record.id,
                "error": str(exc),
            },
        )
        console.print(f"    [red]CRASHED:[/red] {exc}")
        return DefectResult(
            defect_id=record.id,
            category=record.category,
            passed_oracle=False,
            passed_own_tests=False,
            retry_count=0,
            max_retries=max_retries,
            duration_sec=0.0,
            error=str(exc),
            attempts=[],
        )

    sandbox_result = final_state["sandbox_result"]
    passed_own_tests = sandbox_result.passed if sandbox_result else False
    passed_oracle = _grade_against_oracle(record, final_state["current_code"])

    for att in attempts:
        if att.attempt == final_state["retry_count"]:
            att.passed_oracle = passed_oracle

    status = "[green]PASS[/green]" if passed_oracle else "[red]FAIL[/red]"
    console.print(
        f"    {status} -- retries={final_state['retry_count']}/{max_retries}, "
        f"duration={telemetry.duration_sec:.1f}s, "
        f"peak_vram={telemetry.peak_vram_mb:.0f}MB"
        if telemetry.peak_vram_mb is not None
        else f"    {status} -- retries={final_state['retry_count']}/{max_retries}, "
        f"duration={telemetry.duration_sec:.1f}s, peak_vram=N/A"
    )

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
        attempts=attempts,
    )


def evaluate_all(
    structured_llm: Runnable[str, CodeAuditOutput],
    max_retries: int = DEFAULT_MAX_RETRIES,
    console: Console | None = None,
    model_name: str = DEFAULT_MODEL,
) -> EvaluationSummary:
    if console is None:
        console = Console()

    manifest = load_manifest()
    results: list[DefectResult] = []
    total = len(manifest.defects)

    for index, record in enumerate(manifest.defects, start=1):
        logger.info(
            "evaluating_defect",
            extra={"event": "evaluating_defect", "defect_id": record.id},
        )
        result = evaluate_defect(
            record,
            structured_llm,
            max_retries,
            defect_index=index,
            total_defects=total,
            console=console,
        )
        results.append(result)

    pass_at_1 = sum(1 for r in results if r.passed_oracle and r.retry_count == 0)
    pass_overall = sum(1 for r in results if r.passed_oracle)
    durations = [r.duration_sec for r in results]
    vram_values = [r.peak_vram_mb for r in results if r.peak_vram_mb is not None]

    return EvaluationSummary(
        model=model_name,
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


def _print_summary(summary: EvaluationSummary, console: Console) -> None:
    table = Table(title="Benchmark Summary")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Model", summary.model)
    table.add_row("Total defects", str(summary.total_defects))
    table.add_row(
        "Pass@1",
        f"{summary.pass_at_1}/{summary.total_defects} ({summary.pass_at_1_rate:.0%})",
    )
    table.add_row(
        "Pass (overall)",
        f"{summary.pass_overall}/{summary.total_defects} ({summary.pass_overall_rate:.0%})",
    )
    table.add_row("Avg duration", f"{summary.avg_duration_sec:.2f}s")
    vram_line = (
        f"{summary.avg_peak_vram_mb:.0f} MB"
        if summary.avg_peak_vram_mb
        else "N/A (no GPU)"
    )
    table.add_row("Avg peak VRAM", vram_line)
    console.print(table)

    per_defect = Table(title="Per-Defect Results")
    per_defect.add_column("Defect")
    per_defect.add_column("Status")
    per_defect.add_column("Retries")
    per_defect.add_column("Note")

    for result in summary.results:
        status = "[green]PASS[/green]" if result.passed_oracle else "[red]FAIL[/red]"
        note = f"CRASHED: {result.error}" if result.error else ""
        per_defect.add_row(
            result.defect_id,
            status,
            f"{result.retry_count}/{result.max_retries}",
            note,
        )
    console.print(per_defect)


def main() -> None:
    parser = ArgumentParser(description="Run the Patchwork benchmark evaluation suite.")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_PATH,
        help="Path where summary results JSON will be written (default: benchmarks/results.json)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Ollama model name to use for evaluation (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_LLM_TIMEOUT_SEC,
        help=f"Per-call LLM timeout in seconds (default: {DEFAULT_LLM_TIMEOUT_SEC}s).",
    )
    args = parser.parse_args()

    console = Console()
    console.print(f"[cyan]Building structured LLM client ({args.model})...[/cyan]")
    structured_llm = build_structured_llm(model=args.model, timeout=args.timeout)

    console.print(
        f"[cyan]Running 100-defect benchmark ({args.model}). This will take a while...[/cyan]\n"
    )
    start = time.perf_counter()
    summary = evaluate_all(structured_llm, console=console, model_name=args.model)
    elapsed = time.perf_counter() - start

    console.print()
    _print_summary(summary, console)
    console.print(f"\nTotal wall time: {elapsed:.1f}s")

    save_results(summary, path=args.output)
    console.print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
