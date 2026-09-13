def test_summarize_generator():
    gen = (x for x in [1, 2, 2, 3])
    assert summarize_stream(gen) == (4, 3)


def test_empty_generator():
    gen = (x for x in [])
    assert summarize_stream(gen) == (0, 0)