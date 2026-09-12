"""
tests/test_cli.py
====================
Mocks build_structured_llm and build_patchwork_graph -- never touches a
real Ollama server. _run_audit is tested against a fake graph whose
.stream() yields a scripted sequence of states, mirroring how
graph.stream(stream_mode="values") behaves for real. main() is tested
end-to-end against a real temp file on disk, with _run_audit mocked out
so no real graph/LLM machinery runs at that level.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from patchwork.cli import (
    _parse_args,
    _read_target,
    _run_audit,
    _write_outputs,
    main,
)
from patchwork.state import create_initial_state


class TestParseArgs:
    def test_parses_target_path(self) -> None:
        args = _parse_args(["audit", "target.py"])
        assert args.command == "audit"
        assert args.target == Path("target.py")

    def test_heal_flag_defaults_false(self) -> None:
        args = _parse_args(["audit", "target.py"])
        assert args.heal is False

    def test_heal_flag_can_be_set(self) -> None:
        args = _parse_args(["audit", "target.py", "--heal"])
        assert args.heal is True

    def test_max_retries_defaults_to_project_default(self) -> None:
        from patchwork.state import DEFAULT_MAX_RETRIES

        args = _parse_args(["audit", "target.py"])
        assert args.max_retries == DEFAULT_MAX_RETRIES

    def test_max_retries_can_be_overridden(self) -> None:
        args = _parse_args(["audit", "target.py", "--max-retries", "5"])
        assert args.max_retries == 5

    def test_output_dir_defaults_to_cwd(self) -> None:
        args = _parse_args(["audit", "target.py"])
        assert args.output_dir == Path.cwd()

    def test_output_dir_can_be_overridden(self) -> None:
        args = _parse_args(["audit", "target.py", "--output-dir", "out"])
        assert args.output_dir == Path("out")

    def test_missing_command_exits_nonzero(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args([])


class TestReadTarget:
    def test_reads_real_file_contents(self, tmp_path: Path) -> None:
        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")

        assert _read_target(target) == "x = 1\n"


class TestRunAudit:
    def test_returns_final_yielded_state(self) -> None:
        initial = create_initial_state("target.py", "x = 1")

        # avoid **typed_dict unpacking / re-reading through a dict(...)
        # copy in a dict literal -- both erase type info under
        # mypy --strict. Build each audit_trail list as its own typed
        # variable first, then assign it back.
        second_trail: list[str] = [*initial["audit_trail"], "step 2"]
        second_state = dict(initial)
        second_state["audit_trail"] = second_trail

        final_trail: list[str] = [*second_trail, "step 3"]
        final_state = dict(second_state)
        final_state["audit_trail"] = final_trail

        fake_graph = MagicMock()
        fake_graph.stream.return_value = iter([initial, second_state, final_state])

        with (
            patch("patchwork.cli.build_structured_llm"),
            patch("patchwork.cli.build_patchwork_graph", return_value=fake_graph),
        ):
            result = _run_audit(Path("target.py"), "x = 1", max_retries=0)

        assert result == final_state

    def test_passes_max_retries_into_initial_state(self) -> None:
        initial = create_initial_state("target.py", "x = 1", max_retries=2)
        fake_graph = MagicMock()
        fake_graph.stream.return_value = iter([initial])

        with (
            patch("patchwork.cli.build_structured_llm"),
            patch("patchwork.cli.build_patchwork_graph", return_value=fake_graph),
        ):
            result = _run_audit(Path("target.py"), "x = 1", max_retries=2)

        assert result["max_retries"] == 2


class TestWriteOutputs:
    def test_writes_patched_code_and_tests_to_expected_filenames(
        self, tmp_path: Path
    ) -> None:
        state = create_initial_state("target.py", "x = 1")
        state["current_code"] = "x = 2\n"
        state["current_tests"] = "def test_x():\n    assert x == 2\n"

        patched_path, test_path = _write_outputs(Path("target.py"), tmp_path, state)

        assert patched_path == tmp_path / "target_fixed.py"
        assert test_path == tmp_path / "test_target.py"
        assert patched_path.read_text(encoding="utf-8") == "x = 2\n"
        assert (
            test_path.read_text(encoding="utf-8")
            == "def test_x():\n    assert x == 2\n"
        )

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        state = create_initial_state("target.py", "x = 1")
        nested_dir = tmp_path / "nested" / "out"

        _write_outputs(Path("target.py"), nested_dir, state)

        assert nested_dir.exists()


class TestMain:
    def test_target_file_not_found_returns_1(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.py"
        result = main(["audit", str(missing)])
        assert result == 1

    def test_target_is_a_directory_returns_1(self, tmp_path: Path) -> None:
        # reading a directory as if it were a file raises OSError
        # (IsADirectoryError on POSIX), not FileNotFoundError -- covers
        # the second except branch in main()'s target-read guard
        result = main(["audit", str(tmp_path)])
        assert result == 1

    def test_passing_run_returns_0_and_writes_outputs(self, tmp_path: Path) -> None:
        target = tmp_path / "target.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        final_state = create_initial_state(
            str(target), "def add(a, b):\n    return a + b\n"
        )
        final_state["current_code"] = "def add(a, b):\n    return a + b\n"
        final_state["sandbox_result"] = MagicMock(passed=True)

        with patch("patchwork.cli._run_audit", return_value=final_state):
            result = main(["audit", str(target), "--output-dir", str(tmp_path)])

        assert result == 0
        assert (tmp_path / "target_fixed.py").exists()
        assert (tmp_path / "test_target.py").exists()

    def test_failing_run_returns_1(self, tmp_path: Path) -> None:
        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")

        final_state = create_initial_state(str(target), "x = 1\n")
        final_state["sandbox_result"] = MagicMock(passed=False)

        with patch("patchwork.cli._run_audit", return_value=final_state):
            result = main(["audit", str(target), "--output-dir", str(tmp_path)])

        assert result == 1

    def test_no_sandbox_result_returns_1(self, tmp_path: Path) -> None:
        # defensive case: if _run_audit somehow returns before
        # execute_tests ever ran, main() must not crash on
        # sandbox.passed -- it should treat missing result as failure
        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")

        final_state = create_initial_state(str(target), "x = 1\n")
        # sandbox_result stays None, as create_initial_state sets it

        with patch("patchwork.cli._run_audit", return_value=final_state):
            result = main(["audit", str(target), "--output-dir", str(tmp_path)])

        assert result == 1

    def test_heal_flag_off_uses_zero_max_retries(self, tmp_path: Path) -> None:
        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        final_state = create_initial_state(str(target), "x = 1\n")
        final_state["sandbox_result"] = MagicMock(passed=True)

        with patch(
            "patchwork.cli._run_audit", return_value=final_state
        ) as mock_run_audit:
            main(["audit", str(target), "--output-dir", str(tmp_path)])

        assert mock_run_audit.call_args[0][2] == 0  # max_retries positional arg

    def test_heal_flag_on_uses_provided_max_retries(self, tmp_path: Path) -> None:
        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        final_state = create_initial_state(str(target), "x = 1\n")
        final_state["sandbox_result"] = MagicMock(passed=True)

        with patch(
            "patchwork.cli._run_audit", return_value=final_state
        ) as mock_run_audit:
            main(
                [
                    "audit",
                    str(target),
                    "--heal",
                    "--max-retries",
                    "5",
                    "--output-dir",
                    str(tmp_path),
                ]
            )

        assert mock_run_audit.call_args[0][2] == 5
