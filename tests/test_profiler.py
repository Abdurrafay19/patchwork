"""
tests/test_profiler.py
========================
The no-GPU fallback path is mocked (patching pynvml.nvmlInit to raise),
not relied on from the host's actual hardware -- a dev machine with a
real GPU must see identical, deterministic results here as CI (which
has no GPU). Testing against real hardware state would make these tests
flake depending on what machine runs them; that's what
scripts/manual_profiler_test.py is for instead.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pynvml

from patchwork.telemetry.profiler import (
    GPUProfiler,
    TelemetryResult,
    profile_call,
    profile_vram,
)


class TestGPUProfilerNoGPU:
    """Every test here patches pynvml.nvmlInit to force the no-GPU path,
    so results are identical regardless of the host's actual hardware."""

    @patch("patchwork.telemetry.profiler.pynvml.nvmlInit")
    def test_context_manager_does_not_raise_without_gpu(
        self, mock_init: MagicMock
    ) -> None:
        mock_init.side_effect = pynvml.NVMLError_LibraryNotFound()
        with GPUProfiler() as profiler:
            time.sleep(0.05)
        result = profiler.result()
        assert isinstance(result, TelemetryResult)

    @patch("patchwork.telemetry.profiler.pynvml.nvmlInit")
    def test_gpu_available_false_without_driver(self, mock_init: MagicMock) -> None:
        mock_init.side_effect = pynvml.NVMLError_LibraryNotFound()
        with GPUProfiler() as profiler:
            pass
        assert profiler.result().gpu_available is False

    @patch("patchwork.telemetry.profiler.pynvml.nvmlInit")
    def test_peak_vram_none_without_gpu(self, mock_init: MagicMock) -> None:
        mock_init.side_effect = pynvml.NVMLError_LibraryNotFound()
        with GPUProfiler() as profiler:
            pass
        assert profiler.result().peak_vram_mb is None

    @patch("patchwork.telemetry.profiler.pynvml.nvmlInit")
    def test_duration_still_measured_without_gpu(self, mock_init: MagicMock) -> None:
        mock_init.side_effect = pynvml.NVMLError_LibraryNotFound()
        with GPUProfiler(interval=0.01) as profiler:
            time.sleep(0.1)
        result = profiler.result()
        assert result.duration_sec >= 0.1

    @patch("patchwork.telemetry.profiler.pynvml.nvmlInit")
    def test_error_message_populated_when_nvml_unavailable(
        self, mock_init: MagicMock
    ) -> None:
        mock_init.side_effect = pynvml.NVMLError_LibraryNotFound()
        with GPUProfiler() as profiler:
            pass
        assert profiler.result().error_message is not None

    @patch("patchwork.telemetry.profiler.pynvml.nvmlInit")
    def test_result_is_pydantic_model_and_json_serializable(
        self, mock_init: MagicMock
    ) -> None:
        mock_init.side_effect = pynvml.NVMLError_LibraryNotFound()
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
