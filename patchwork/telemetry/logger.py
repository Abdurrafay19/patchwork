from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

DEFAULT_TELEMETRY_PATH: Final[Path] = Path("telemetry.json")

_RESERVED_LOG_RECORD_ATTRS: Final[frozenset[str]] = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=None, exc_info=None
    ).__dict__.keys()
)


class JsonLogFormatter(logging.Formatter):
    """Renders each log record as one JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_ATTRS
        }
        payload.update(extra_fields)
        return json.dumps(payload, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Configures the patchwork logger tree to emit JSON lines to stderr."""
    root = logging.getLogger("patchwork")
    root.setLevel(level)

    already_configured = any(
        isinstance(handler.formatter, JsonLogFormatter) for handler in root.handlers
    )
    if already_configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)
    root.propagate = False


class TelemetryLogEntry(BaseModel):
    """One row of the persistent telemetry.json log -- one per CLI/eval run."""

    timestamp: str
    source_file_path: str
    tests_passed: bool | None = None
    retry_count: int
    max_retries: int
    duration_sec: float = Field(ge=0.0)
    peak_vram_mb: float | None = None
    gpu_available: bool = False


def append_telemetry_entry(
    entry: TelemetryLogEntry, path: Path = DEFAULT_TELEMETRY_PATH
) -> None:
    """Appends one telemetry entry as a JSON line to path."""
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json())
        f.write("\n")


def read_telemetry_entries(
    path: Path = DEFAULT_TELEMETRY_PATH,
) -> list[TelemetryLogEntry]:
    """Reads all telemetry entries back from a JSON Lines file."""
    if not path.exists():
        return []
    entries: list[TelemetryLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(TelemetryLogEntry.model_validate_json(line))
    return entries
