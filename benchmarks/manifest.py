"""
benchmarks.manifest
=====================
Schema for the 25-defect benchmark dataset. Each defect has a buggy
source file AND a separate oracle test file the agent never sees --
evaluate.py grades against the oracle, not the SLM's own self-written
tests, since a model that writes weak tests would otherwise score as
"fixed" even when it isn't.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, model_validator

DATASET_DIR: Final[Path] = Path(__file__).parent / "dataset"
ORACLE_TESTS_DIR: Final[Path] = DATASET_DIR / "oracle_tests"
MANIFEST_PATH: Final[Path] = DATASET_DIR / "manifest.json"


class DefectRecord(BaseModel):
    id: str = Field(min_length=1)  # e.g. "mutable_default_01"
    category: str = Field(min_length=1)  # e.g. "mutable_default_arguments"
    source_filename: str = Field(min_length=1)  # relative to dataset/
    oracle_test_filename: str = Field(min_length=1)  # relative to dataset/oracle_tests/
    description: str = Field(min_length=1)


class DefectManifest(BaseModel):
    defects: list[DefectRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_ids(self) -> DefectManifest:
        # a duplicate id would let one defect silently shadow another in
        # any dict/lookup keyed by id (evaluate.py's test _record() helper
        # does exactly that) -- fail loudly at load time, not later at an
        # unrelated call site
        seen: set[str] = set()
        duplicates: set[str] = set()
        for defect in self.defects:
            if defect.id in seen:
                duplicates.add(defect.id)
            seen.add(defect.id)
        if duplicates:
            raise ValueError(
                f"Duplicate defect id(s) in manifest: {sorted(duplicates)}"
            )
        return self


def load_manifest(path: Path = MANIFEST_PATH) -> DefectManifest:
    return DefectManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_defect_source(record: DefectRecord) -> str:
    return (DATASET_DIR / record.source_filename).read_text(encoding="utf-8")


def load_oracle_test(record: DefectRecord) -> str:
    return (ORACLE_TESTS_DIR / record.oracle_test_filename).read_text(encoding="utf-8")
