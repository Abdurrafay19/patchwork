def test_stream_average_generator():
    gen = (x for x in [10, 20, 30])
    assert compute_stream_average(gen) == 20.0


def test_empty_generator():
    gen = (x for x in [])
    assert compute_stream_average(gen) == 0.0