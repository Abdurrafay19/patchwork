def test_finds_last_element():
    assert binary_search([1, 3, 5, 7, 9], 9) == 4


def test_finds_first_element():
    assert binary_search([1, 3, 5, 7, 9], 1) == 0


def test_missing_target_returns_negative_one():
    assert binary_search([1, 3, 5, 7, 9], 4) == -1
