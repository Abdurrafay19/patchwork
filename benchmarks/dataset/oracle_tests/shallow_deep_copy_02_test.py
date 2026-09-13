def test_duplicate_has_same_values():
    matrix = [[1, 2], [3, 4]]
    dup = duplicate_matrix(matrix)
    assert dup == [[1, 2], [3, 4]]


def test_mutating_duplicate_row_does_not_affect_original():
    matrix = [[1, 2], [3, 4]]
    dup = duplicate_matrix(matrix)
    dup[0].append(99)
    assert matrix[0] == [1, 2]
