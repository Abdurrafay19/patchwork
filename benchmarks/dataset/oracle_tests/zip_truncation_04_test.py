import pytest


def test_matching_students():
    assert combine_scores(["Bob", "Carol"], [88, 92]) == {
        "Bob": 88,
        "Carol": 92,
    }


def test_unequal_student_scores_raises():
    with pytest.raises(ValueError):
        combine_scores(["Bob", "Carol", "Dave"], [88, 92])
