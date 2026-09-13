"""Calculates the range (max - min) of values from an iterable or generator."""


def calculate_range(stream):
    return max(stream) - min(stream)