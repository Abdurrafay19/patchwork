"""
tests/test_manifest.py
=========================
Loads the real manifest.json and real dataset files -- no mocking,
since this module's whole job is reading real files off disk correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from benchmarks.manifest import (
    DefectManifest,
    load_defect_source,
    load_manifest,
    load_oracle_test,
)


class TestLoadManifest:
    def test_loads_all_current_defects(self) -> None:
        manifest = load_manifest()
        assert len(manifest.defects) >= 5

    def test_every_defect_has_required_fields(self) -> None:
        manifest = load_manifest()
        for record in manifest.defects:
            assert record.id
            assert record.category
            assert record.source_filename
            assert record.oracle_test_filename
            assert record.description

    def test_ids_are_unique(self) -> None:
        manifest = load_manifest()
        ids = [record.id for record in manifest.defects]
        assert len(ids) == len(set(ids))

    def test_duplicate_id_raises_at_load_time(self) -> None:
        # covers _check_unique_ids directly -- the real manifest.json
        # never has duplicates, so this constructs one by hand to prove
        # the validator itself fires, not just that the shipped file
        # happens to be clean
        duplicate_json = (
            '{"defects": ['
            '{"id": "dup", "category": "x", "source_filename": "a.py", '
            '"oracle_test_filename": "a_test.py", "description": "d1"},'
            '{"id": "dup", "category": "x", "source_filename": "b.py", '
            '"oracle_test_filename": "b_test.py", "description": "d2"}'
            "]}"
        )
        with pytest.raises(ValidationError):
            DefectManifest.model_validate_json(duplicate_json)


class TestLoadDefectFiles:
    def test_every_source_file_exists_and_loads(self) -> None:
        manifest = load_manifest()
        for record in manifest.defects:
            source = load_defect_source(record)
            assert len(source) > 0

    def test_every_oracle_test_file_exists_and_loads(self) -> None:
        manifest = load_manifest()
        for record in manifest.defects:
            oracle = load_oracle_test(record)
            assert len(oracle) > 0
            assert "def test_" in oracle
