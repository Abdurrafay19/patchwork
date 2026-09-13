import pytest


def test_matching_score():
    assert check_matching_answers(["A", "B", "C"], ["A", "D", "C"]) == 2


def test_missing_answers_raises_value_error():
    with pytest.raises(ValueError):
        check_matching_answers(["A", "B"], ["A", "B", "C"])
