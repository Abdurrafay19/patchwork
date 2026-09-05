"""
tests/test_profiler.py
========================
This sandbox and CI both have no NVIDIA GPU, so every test here runs
against the real no-GPU fallback path -- which is exactly the path that
matters most to get right, since it's the one CI will always exercise.
"""

from __future__ import annotations

import time

from patchwork.telemetry.profiler import (
    GPUProfiler,
    TelemetryResult,
    profile_call,
    profile_vram,
)


class TestGPUProfilerNoGPU:
    def test_context_manager_does_not_raise_without_gpu(self) -> None:
        with GPUProfiler() as profiler:
            time.sleep(0.05)
        result = profiler.result()
        assert isinstance(result, TelemetryResult)

    def test_gpu_available_false_without_driver(self) -> None:
        with GPUProfiler() as profiler:
            pass
        assert profiler.result().gpu_available is False

    def test_peak_vram_none_without_gpu(self) -> None:
        with GPUProfiler() as profiler:
            pass
        assert profiler.result().peak_vram_mb is None

    def test_duration_still_measured_without_gpu(self) -> None:
        with GPUProfiler(interval=0.01) as profiler:
            time.sleep(0.1)
        result = profiler.result()
        assert result.duration_sec >= 0.1

    def test_error_message_populated_when_nvml_unavailable(self) -> None:
        with GPUProfiler() as profiler:
            pass
        assert profiler.result().error_message is not None

    def test_result_is_pydantic_model_and_json_serializable(self) -> None:
        with GPUProfiler() as profiler:
            pass
        payload = profiler.result().model_dump_json()
        assert isinstance(payload, str)
        assert '"gpu_available":false' in payload.replace(" ", "")


class TestProfileCall:
    def test_returns_function_result_unchanged(self) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        result, telemetry = profile_call(add, 2, 3)
        assert result == 5
        assert isinstance(telemetry, TelemetryResult)

    def test_supports_kwargs(self) -> None:
        def greet(name: str, greeting: str = "hello") -> str:
            return f"{greeting}, {name}"

        result, _telemetry = profile_call(greet, name="world", greeting="hi")
        assert result == "hi, world"

    def test_exception_in_wrapped_function_propagates(self) -> None:
        def boom() -> None:
            raise ValueError("intentional")

        try:
            profile_call(boom)
            raised = False
        except ValueError:
            raised = True
        assert raised  # profiling must not swallow the caller's own errors


class TestProfileVramDecorator:
    def test_decorated_function_returns_original_result(self) -> None:
        @profile_vram
        def multiply(a: int, b: int) -> int:
            return a * b

        assert multiply(4, 5) == 20

    def test_decorator_preserves_function_name(self) -> None:
        # without functools.wraps, this would be "wrapper" instead --
        # matters for debugging/logging where you inspect __name__
        @profile_vram
        def my_function() -> int:
            return 1

        assert my_function.__name__ == "my_function"