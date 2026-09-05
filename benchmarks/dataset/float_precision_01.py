"""Checks whether a + b equals expected, treating floating-point
rounding error as an acceptable match."""


def is_total_correct(a, b, expected):
    return a + b == expected
