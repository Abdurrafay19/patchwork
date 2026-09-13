"""Merges an extra dict of overrides into a base config, returning a
new merged dict. Mutating a nested value in the merged result must not
affect the original base config."""

import copy


def merge_configs(base, extra):
    merged = copy.copy(base)
    merged.update(extra)
    return merged
