"""
scripts/manual_profiler_test.py
==================================
tests/test_profiler.py only proves the no-GPU fallback path (that's all
CI/this sandbox has). This script is the only way to confirm the actual
positive path -- gpu_available=True and a plausible VRAM number -- since
that requires a real NVIDIA GPU running real inference.

Usage:
    python scripts/manual_profiler_test.py
"""

from __future__ import annotations

from patchwork.graph import build_patchwork_graph, build_structured_llm
from patchwork.state import create_initial_state
from patchwork.telemetry.profiler import GPUProfiler, profile_call

BUGGY_SOURCE = "def add(a, b):\n    return a - b\n"


def main() -> None:
    print("Building structured LLM client and graph...")
    structured_llm = build_structured_llm()
    graph = build_patchwork_graph(structured_llm)
    initial = create_initial_state("manual_profiler_target.py", BUGGY_SOURCE)

    print("Running one audit pass wrapped in GPUProfiler...\n")
    result, telemetry = profile_call(graph.invoke, initial)

    print(f"gpu_available: {telemetry.gpu_available}")
    print(f"peak_vram_mb:  {telemetry.peak_vram_mb}")
    print(f"duration_sec:  {round(telemetry.duration_sec, 2)}")
    print(f"error_message: {telemetry.error_message}")

    if not telemetry.gpu_available:
        print("\nWARNING: gpu_available is False. Either nvidia-ml-py can't see your")
        print("GPU, or Ollama is running on CPU. Check `nvidia-smi` and `ollama ps`")
        print(
            "(the PROCESSOR column should say 100% GPU) before trusting benchmark numbers."
        )
    else:
        target_max = 3400  # <=3.4GB Q8_0 ceiling from project spec
        if telemetry.peak_vram_mb is not None and telemetry.peak_vram_mb > target_max:
            print(
                f"\nNOTE: peak VRAM ({telemetry.peak_vram_mb:.0f}MB) exceeds your project's"
            )
            print(
                f"target ceiling of {target_max}MB -- worth investigating before benchmarking."
            )

    print(
        f"\nSandbox passed: {result['sandbox_result'].passed if result['sandbox_result'] else 'N/A'}"
    )

    # Second run: raw context manager, for comparing against profile_call's
    # numbers -- they should be close but not identical (profiling overhead).
    print("\n--- Second run via raw GPUProfiler context manager ---")
    with GPUProfiler(interval=0.02) as profiler:
        graph.invoke(create_initial_state("manual_profiler_target_2.py", BUGGY_SOURCE))
    r2 = profiler.result()
    print(f"peak_vram_mb: {r2.peak_vram_mb}, duration_sec: {round(r2.duration_sec, 2)}")


if __name__ == "__main__":
    main()