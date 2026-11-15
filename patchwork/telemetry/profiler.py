from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Final, TypeVar

if TYPE_CHECKING:
    import pynvml

    _HAS_PYNVML = True
else:
    try:
        import pynvml

        _HAS_PYNVML = True
    except ImportError:  # pragma: no cover
        pynvml = None
        _HAS_PYNVML = False
from pydantic import BaseModel, Field

logger = logging.getLogger("patchwork.telemetry.profiler")

DEFAULT_POLL_INTERVAL_SEC: Final[float] = 0.05
DEFAULT_DEVICE_INDEX: Final[int] = 0

T = TypeVar("T")


class TelemetryResult(BaseModel):
    duration_sec: float = Field(ge=0.0)
    peak_vram_mb: float | None = None  # None if no GPU / nvml unavailable
    gpu_available: bool = False
    error_message: str | None = None  # only for nvml-level failures, not "no GPU"


class GPUProfiler:
    """Context manager that tracks peak GPU VRAM usage during execution."""

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
        if not _HAS_PYNVML or pynvml is None:
            self.error_message = "pynvml is not installed"
            return

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
