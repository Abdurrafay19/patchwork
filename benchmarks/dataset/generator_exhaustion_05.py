"""Returns a tuple of (total_count, unique_count) for an item stream."""


def summarize_stream(stream):
    total = len(list(stream))
    unique = len(set(stream))
    return total, unique