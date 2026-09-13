def test_unique_matrix_rows():
    matrix = [[1, 2], [3, 4], [1, 2]]
    result = get_unique_matrix_rows(matrix)
    assert len(result) == 2
    assert [1, 2] in result
    assert [3, 4] in result
