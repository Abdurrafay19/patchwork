def test_joins_strings():
    assert csv_join(["a", "b", "c"]) == "a,b,c"


def test_joins_non_string_values():
    assert csv_join([1, 2, 3]) == "1,2,3"
