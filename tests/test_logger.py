"""
tests/test_logger.py
=======================
Tests for patchwork.telemetry.logger. JsonLogFormatter is tested by
constructing real LogRecord objects directly (no full logging pipeline
needed to verify formatting); append/read round-trips use tmp_path so
nothing touches the real telemetry.json on disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from patchwork.telemetry.logger import (
    JsonLogFormatter,
    TelemetryLogEntry,
    append_telemetry_entry,
    configure_json_logging,
    read_telemetry_entries,
)


def _make_record(
    msg: str = "hello", extra: dict[str, object] | None = None
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="patchwork.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


class TestJsonLogFormatter:
    def test_output_is_valid_json(self) -> None:
        formatter = JsonLogFormatter()
        record = _make_record()
        payload = json.loads(formatter.format(record))
        assert isinstance(payload, dict)

    def test_includes_standard_fields(self) -> None:
        formatter = JsonLogFormatter()
        record = _make_record(msg="something happened")
        payload = json.loads(formatter.format(record))
        assert payload["message"] == "something happened"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "patchwork.test"
        assert "timestamp" in payload

    def test_includes_extra_fields_from_call_site(self) -> None:
        # mirrors how sandbox.py/linter.py/graph.py actually log:
        # extra={"event": "...", "passed": True, ...}
        formatter = JsonLogFormatter()
        record = _make_record(
            msg="sandbox_run_complete",
            extra={"event": "sandbox_run_complete", "passed": True, "returncode": 0},
        )
        payload = json.loads(formatter.format(record))
        assert payload["event"] == "sandbox_run_complete"
        assert payload["passed"] is True
        assert payload["returncode"] == 0

    def test_does_not_leak_internal_logrecord_attrs(self) -> None:
        # e.g. "args", "exc_info", "pathname" are LogRecord internals,
        # not application data -- they must not appear in the JSON output
        formatter = JsonLogFormatter()
        record = _make_record()
        payload = json.loads(formatter.format(record))
        assert "args" not in payload
        assert "exc_info" not in payload

    def test_non_serializable_extra_value_falls_back_to_str(self) -> None:
        # default=str in json.dumps -- an object with no native JSON
        # representation must not crash formatting
        formatter = JsonLogFormatter()
        record = _make_record(extra={"event": "x", "obj": object()})
        payload_str = formatter.format(record)  # must not raise
        payload = json.loads(payload_str)
        assert "obj" in payload


class TestConfigureJsonLogging:
    def test_attaches_a_handler(self) -> None:
        root = logging.getLogger("patchwork")
        root.handlers.clear()  # isolate from other tests/modules

        configure_json_logging()

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonLogFormatter)

    def test_calling_twice_does_not_duplicate_handlers(self) -> None:
        root = logging.getLogger("patchwork")
        root.handlers.clear()

        configure_json_logging()
        configure_json_logging()

        assert len(root.handlers) == 1

    def test_disables_propagation(self) -> None:
        root = logging.getLogger("patchwork")
        root.handlers.clear()

        configure_json_logging()

        assert root.propagate is False


class TestTelemetryPersistence:
    def test_append_then_read_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.json"
        entry = TelemetryLogEntry(
            timestamp="2026-01-01T00:00:00Z",
            source_file_path="target.py",
            tests_passed=True,
            retry_count=1,
            max_retries=3,
            duration_sec=4.2,
            peak_vram_mb=2600.0,
            gpu_available=True,
        )

        append_telemetry_entry(entry, path=path)
        entries = read_telemetry_entries(path=path)

        assert len(entries) == 1
        assert entries[0] == entry

    def test_multiple_appends_accumulate_as_separate_lines(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "telemetry.json"
        entry_a = TelemetryLogEntry(
            timestamp="2026-01-01T00:00:00Z",
            source_file_path="a.py",
            retry_count=0,
            max_retries=0,
            duration_sec=1.0,
        )
        entry_b = TelemetryLogEntry(
            timestamp="2026-01-01T00:01:00Z",
            source_file_path="b.py",
            retry_count=0,
            max_retries=0,
            duration_sec=2.0,
        )

        append_telemetry_entry(entry_a, path=path)
        append_telemetry_entry(entry_b, path=path)
        entries = read_telemetry_entries(path=path)

        assert len(entries) == 2
        assert entries[0].source_file_path == "a.py"
        assert entries[1].source_file_path == "b.py"

    def test_reading_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        path = tmp_path / "does_not_exist.json"
        assert read_telemetry_entries(path=path) == []

    def test_blank_lines_in_file_are_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.json"
        entry = TelemetryLogEntry(
            timestamp="2026-01-01T00:00:00Z",
            source_file_path="a.py",
            retry_count=0,
            max_retries=0,
            duration_sec=1.0,
        )
        append_telemetry_entry(entry, path=path)
        # simulate a stray trailing blank line, which a hand-edited or
        # partially-written file could plausibly contain
        with path.open("a", encoding="utf-8") as f:
            f.write("\n")

        entries = read_telemetry_entries(path=path)
        assert len(entries) == 1
