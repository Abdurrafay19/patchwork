"""
scripts/manual_smoke_test.py
==============================
Not part of the test suite, not run in CI -- CI has no GPU and no Ollama
server. This is a manual, human-run check against your real local model,
to see what qwen2.5-coder:3b actually returns before you build the
retry loop on top of it.

Usage:
    python scripts/manual_smoke_test.py
"""

from __future__ import annotations

import time

from patchwork.graph import build_patchwork_graph, build_structured_llm
from patchwork.state import create_initial_state

# deliberately buggy: uses + instead of /
BUGGY_SOURCE = "def divide(a, b):\n    return a + b\n"


def main() -> None:
    print(
        "Building structured LLM client (qwen2.5-coder:3b, temp=0.1, num_ctx=8192)..."
    )
    structured_llm = build_structured_llm()

    print("Compiling graph...")
    graph = build_patchwork_graph(structured_llm)

    print("Running against buggy source:")
    print(BUGGY_SOURCE)

    initial = create_initial_state("manual_test_target.py", BUGGY_SOURCE)

    start = time.perf_counter()
    final = graph.invoke(initial)
    elapsed = time.perf_counter() - start

    print(f"\n--- Done in {elapsed:.2f}s ---\n")
    print("Audit trail:")
    for line in final["audit_trail"]:
        print(f"  - {line}")

    print("\nFinal patched code:")
    print(final["current_code"])

    print("\nGenerated tests:")
    print(final["current_tests"])

    sandbox = final["sandbox_result"]
    print(f"\nTests passed: {sandbox.passed if sandbox else 'N/A'}")
    if sandbox and not sandbox.passed:
        print(f"stderr:\n{sandbox.stderr}")


if __name__ == "__main__":
    main()