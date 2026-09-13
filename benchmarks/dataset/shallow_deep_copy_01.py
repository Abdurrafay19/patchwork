"""Returns a clone of a record dict. Mutating a nested value on the
clone must not affect the original record."""

import copy


def clone_record(record):
    return copy.copy(record)
