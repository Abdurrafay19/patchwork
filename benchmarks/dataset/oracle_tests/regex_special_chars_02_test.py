def test_subpattern_with_plus_sign():
    assert contains_exact_subpattern("111=3", "1+1") is False


def test_literal_match():
    assert contains_exact_subpattern("formula: 1+1=2", "1+1") is True
