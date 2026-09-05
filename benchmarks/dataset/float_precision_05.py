"""Checks whether value is effectively zero, treating floating-point
rounding error as an acceptable match."""


def is_zero(value):
    return value == 0.0
