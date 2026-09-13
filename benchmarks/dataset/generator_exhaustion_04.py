"""Joins all string items yielded by a generator into a comma-separated string if non-empty."""


def join_stream_items(stream):
    first = next(stream, None)
    if first is None:
        return ""
    return ",".join(stream)