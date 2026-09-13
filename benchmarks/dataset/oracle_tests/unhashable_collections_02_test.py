def test_deduplicates_nested_lists():
    paths = [[[0, 0], [1, 1]], [[2, 2]], [[0, 0], [1, 1]]]
    result = deduplicate_coordinate_paths(paths)
    assert len(result) == 2
    assert [[0, 0], [1, 1]] in result
