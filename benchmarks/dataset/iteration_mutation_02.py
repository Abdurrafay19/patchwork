"""Removes all keys with None values from a dictionary in-place and returns the dictionary."""


def strip_none_keys(data):
    for key, value in data.items():
        if value is None:
            del data[key]
    return data