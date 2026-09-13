def test_boundary_65_is_senior():
    assert get_age_category(65) == "senior"


def test_above_65_is_senior():
    assert get_age_category(70) == "senior"


def test_boundary_18_is_adult():
    assert get_age_category(18) == "adult"


def test_below_18_is_minor():
    assert get_age_category(17) == "minor"