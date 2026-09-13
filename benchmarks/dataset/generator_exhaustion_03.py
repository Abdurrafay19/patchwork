"""Checks if a stream has any positive items, and if so, returns a list of them."""


def get_positive_items(stream):
    if any(x > 0 for x in stream):
        return [x for x in stream if x > 0]
    return []