"""
patchwork.cli
==============
Command-line entry point: python -m patchwork.cli audit target.py --heal

Dual-output pattern (see Output_Handling doc): rich renders live progress
to the terminal while the graph runs; the patched source and generated
test suite are always written to disk afterward, so results survive
after the console closes.
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Final

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from patchwork.graph import build_patchwork_graph, build_structured_llm
from patchwork.state import DEFAULT_MAX_RETRIES, AgentState, create_initial_state
from patchwork.telemetry.profiler import GPUProfiler

console: Final = Console()


def _parse_args(argv: list[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        prog="patchwork",
        description="Local self-healing code-audit and test-generation agent.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit", help="Audit a Python file, optionally self-healing test failures."
    )
    audit_parser.add_argument(
        "target", type=Path, help="Path to the Python file to audit."
    )
    audit_parser.add_argument(
        "--heal",
        action="store_true",
        help="Enable the reflect-and-heal retry loop on test failure. "
        "Without this flag, the agent makes one pass and reports the result.",
    )
    audit_parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=f"Max reflection retries when --heal is set (default: {DEFAULT_MAX_RETRIES}).",
    )
    audit_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to write the patched file and test suite into (default: cwd).",
    )

    return parser.parse_args(argv)


def _read_target(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_audit(target_path: Path, source: str, max_retries: int) -> AgentState:
    console.print("[cyan]Building structured LLM client (qwen2.5-coder:3b)...[/cyan]")
    structured_llm = build_structured_llm()
    graph = build_patchwork_graph(structured_llm)

    initial = create_initial_state(str(target_path), source, max_retries=max_retries)

    final_state: AgentState = initial
    with console.status("[yellow]Starting audit...[/yellow]") as status:
        # stream_mode="values" yields the full state after each node --
        # audit_trail's newest entry is exactly what that node just did
        for state in graph.stream(initial, stream_mode="values"):
            final_state = state  # type: ignore[assignment]
            latest_entry = state["audit_trail"][-1]
            status.update(f"[yellow]{latest_entry}[/yellow]")
            console.print(f"  [dim]->[/dim] {latest_entry}")

    return final_state


def _print_patched_code(state: AgentState) -> None:
    console.rule("[bold]Patched Code[/bold]")
    console.print(
        Syntax(state["current_code"], "python", theme="ansi_dark", line_numbers=True)
    )


def _print_summary_table(
    state: AgentState, duration_sec: float, peak_vram_mb: float | None
) -> None:
    table = Table(title="Run Summary")
    table.add_column("Metric")
    table.add_column("Value")

    sandbox = state["sandbox_result"]
    table.add_row("Tests passed", str(sandbox.passed) if sandbox else "N/A")
    table.add_row("Retry count", f"{state['retry_count']} / {state['max_retries']}")
    table.add_row("Duration", f"{duration_sec:.2f}s")
    table.add_row(
        "Peak VRAM",
        f"{peak_vram_mb:.0f} MB" if peak_vram_mb is not None else "N/A (no GPU)",
    )

    console.print(table)


def _write_outputs(
    target_path: Path, output_dir: Path, state: AgentState
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = target_path.stem

    patched_path = output_dir / f"{stem}_fixed.py"
    test_path = output_dir / f"test_{stem}.py"

    patched_path.write_text(state["current_code"], encoding="utf-8")
    test_path.write_text(state["current_tests"], encoding="utf-8")

    return patched_path, test_path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.command != "audit":
        console.print(f"[red]Unknown command:[/red] {args.command}")
        return 1

    try:
        source = _read_target(args.target)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] target file not found: {args.target}")
        return 1
    except OSError as exc:
        console.print(f"[red]Error:[/red] could not read {args.target}: {exc}")
        return 1

    max_retries = args.max_retries if args.heal else 0

    with GPUProfiler() as profiler:
        final_state = _run_audit(args.target, source, max_retries)
    telemetry = profiler.result()

    _print_patched_code(final_state)
    _print_summary_table(final_state, telemetry.duration_sec, telemetry.peak_vram_mb)

    patched_path, test_path = _write_outputs(args.target, args.output_dir, final_state)
    console.print(f"\n[green]Patched code written to:[/green] {patched_path}")
    console.print(f"[green]Test suite written to:[/green] {test_path}")

    sandbox = final_state["sandbox_result"]
    return 0 if sandbox is not None and sandbox.passed else 1


if __name__ == "__main__":
    sys.exit(main())
