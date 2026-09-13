"""Returns the average (mean) of numbers yielded by an iterable or generator."""


def compute_stream_average(stream):
    total = sum(stream)
    count = len(list(stream))
    return total / count if count > 0 else 0.0