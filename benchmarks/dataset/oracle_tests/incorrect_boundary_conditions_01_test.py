def test_boundary_90_is_a():
    assert get_letter_grade(90) == "A"


def test_boundary_80_is_b():
    assert get_letter_grade(80) == "B"


def test_above_90_is_a():
    assert get_letter_grade(95) == "A"


def test_below_70_is_f():
    assert get_letter_grade(65) == "F"
