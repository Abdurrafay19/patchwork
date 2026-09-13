def test_joins_all_items_including_first():
    gen = (str(x) for x in ["apple", "banana", "cherry"])
    assert join_stream_items(gen) == "apple,banana,cherry"


def test_empty_stream():
    gen = (str(x) for x in [])
    assert join_stream_items(gen) == ""