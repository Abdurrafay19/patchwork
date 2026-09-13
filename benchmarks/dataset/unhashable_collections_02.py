"""Deduplicates a list of coordinate path sequences (each path is a list of [x, y] coordinates)."""


def deduplicate_coordinate_paths(paths):
    return list(set(paths))
