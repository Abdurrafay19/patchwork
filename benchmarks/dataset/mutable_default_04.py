"""Increments the count for a key in a counts dictionary and returns
it. Each call with no explicit counts argument should start from an
empty dictionary."""


def increment_count(key, counts={}):
    counts[key] = counts.get(key, 0) + 1
    return counts