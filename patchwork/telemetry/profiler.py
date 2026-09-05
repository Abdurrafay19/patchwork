"""
patchwork.telemetry.profiler
==============================
VRAM and wall-clock telemetry, kept fully decoupled from graph.py and
the tools -- nothing in the agent logic needs to know this exists.
Used by benchmarks/evaluate.py to wrap graph.invoke() calls.

Must never crash when no NVIDIA GPU is present (CI runs on ubuntu-latest
with no GPU) -- gpu_available=False + peak_vram_mb=None is the correct
degraded result, not an exception.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Final, ParamSpec, TypeVar

import pynvml  # type: ignore[import-untyped]  # nvidia-ml-py ships no py.typed marker
from pydantic import BaseModel, Field

logger = logging.getLogger("patchwork.telemetry.profiler")

DEFAULT_POLL_INTERVAL_SEC: Final[float] = 0.05
DEFAULT_DEVICE_INDEX: Final[int] = 0

P = ParamSpec("P")
T = TypeVar("T")


class TelemetryResult(BaseModel):
    duration_sec: float = Field(ge=0.0)
    peak_vram_mb: float | None = None  # None if no GPU / nvml unavailable
    gpu_available: bool = False
    error_message: str | None = None  # only for nvml-level failures, not "no GPU"


class GPUProfiler:
    """Context manager. Polls VRAM usage on a background thread while the
    `with` block runs, tracks the peak. Falls back cleanly to
    gpu_available=False if no NVIDIA GPU/driver is present -- this is
    the expected path in CI, not an error condition.
    """

    def __init__(
        self,
        device_index: int = DEFAULT_DEVICE_INDEX,
        interval: float = DEFAULT_POLL_INTERVAL_SEC,
    ) -> None:
        self.device_index = device_index
        self.interval = interval
        self.peak_vram_mb: float | None = None
        self.gpu_available = False
        self.error_message: str | None = None
        self.duration_sec: float = 0.0

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0

    def _monitor(self) -> None:
        try:
            pynvml.nvmlInit()
        except pynvml.NVMLError as exc:
            # no driver / no GPU -- expected on CI, not a crash
            self.error_message = str(exc)
            return

        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(self.device_index)
        except pynvml.NVMLError as exc:
            self.error_message = str(exc)
            pynvml.nvmlShutdown()
            return

        self.gpu_available = True
        self.peak_vram_mb = 0.0

        while not self._stop_event.is_set():
            try:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            except pynvml.NVMLError as exc:
                # device disappeared mid-run (driver reset, etc) -- stop
                # polling rather than crash the profiling thread
                logger.warning(
                    "gpu_poll_failed",
                    extra={"event": "gpu_poll_failed", "error": str(exc)},
                )
                break
            used_mb = mem_info.used / (1024 * 1024)
            self.peak_vram_mb = max(self.peak_vram_mb, used_mb)
            self._stop_event.wait(self.interval)

        pynvml.nvmlShutdown()

    def __enter__(self) -> GPUProfiler:  # noqa: PYI034  # typing.Self needs 3.11+, project supports 3.10
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.duration_sec = time.perf_counter() - self._start_time
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 5)

    def result(self) -> TelemetryResult:
        return TelemetryResult(
            duration_sec=self.duration_sec,
            peak_vram_mb=self.peak_vram_mb,
            gpu_available=self.gpu_available,
            error_message=self.error_message,
        )


def profile_call(
    func: Callable[..., T], *args: object, **kwargs: object
) -> tuple[T, TelemetryResult]:
    """Runs func(*args, **kwargs) under a GPUProfiler, returns (result, telemetry)."""
    with GPUProfiler() as profiler:
        result = func(*args, **kwargs)
    return result, profiler.result()


def profile_vram(func: Callable[P, T]) -> Callable[P, T]:
    """Transparent decorator: wraps func in a GPUProfiler, logs the
    telemetry, and returns func's original result unchanged. For call
    sites that just want VRAM logging without touching their return
    signature (business logic stays untouched, per the isolation rule).
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with GPUProfiler() as profiler:
            result = func(*args, **kwargs)
        telemetry = profiler.result()
        logger.info(
            "profiled_call",
            extra={
                "event": "profiled_call",
                "function": func.__name__,
                "duration_sec": round(telemetry.duration_sec, 3),
                "peak_vram_mb": telemetry.peak_vram_mb,
                "gpu_available": telemetry.gpu_available,
            },
        )
        return result

    return wrapper