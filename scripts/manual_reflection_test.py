"""
scripts/manual_reflection_test.py
====================================
Day 2's smoke test used a one-line bug the model fixes on attempt 1 --
that never exercises node_reflect_and_heal or route_after_execution.
This script uses a nastier multi-symptom bug deliberately chosen to be
harder to fix correctly in one shot, so you can watch retry_count go
above 0 for real, not just in the mocked tests.

Usage:
    python scripts/manual_reflection_test.py
"""

from __future__ import annotations

import time

from patchwork.graph import build_patchwork_graph, build_structured_llm
from patchwork.state import create_initial_state

# Multiple bugs stacked in one function: mutable default arg, wrong
# comparison operator, and an off-by-one on the slice. A model that
# fixes only one or two of these on attempt 1 will fail the generated
# tests and should trigger at least one reflection cycle.
BUGGY_SOURCE = (
    "def top_n_scores(scores, n, seen=[]):\n"
    "    seen.append(len(scores))\n"
    "    sorted_scores = sorted(scores)\n"
    "    return sorted_scores[0:n-1]\n"
)


def main() -> None:
    print("Building structured LLM client...")
    structured_llm = build_structured_llm()

    print("Compiling graph...")
    graph = build_patchwork_graph(structured_llm)

    print("Running against multi-bug source (mutable default + off-by-one slice):")
    print(BUGGY_SOURCE)

    # max_retries=3 to give the loop room to actually iterate
    initial = create_initial_state(
        "manual_reflection_target.py", BUGGY_SOURCE, max_retries=3
    )

    start = time.perf_counter()
    final = graph.invoke(initial)
    elapsed = time.perf_counter() - start

    print(f"\n--- Done in {elapsed:.2f}s ---\n")
    print("Audit trail:")
    for line in final["audit_trail"]:
        print(f"  - {line}")

    print(f"\nRetry count used: {final['retry_count']} / {final['max_retries']}")
    if final["retry_count"] == 0:
        print(
            "NOTE: reflection loop was never triggered -- model fixed it on attempt 1."
        )
        print(
            "Try a harder bug in BUGGY_SOURCE if you specifically need to see reflect fire."
        )

    print("\nFinal patched code:")
    print(final["current_code"])

    print("\nGenerated tests:")
    print(final["current_tests"])

    sandbox = final["sandbox_result"]
    print(f"\nTests passed: {sandbox.passed if sandbox else 'N/A'}")
    if sandbox and not sandbox.passed:
        print(f"Final failure output:\n{sandbox.stderr or sandbox.stdout}")


if __name__ == "__main__":
    main()