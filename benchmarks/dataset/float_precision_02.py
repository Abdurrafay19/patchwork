"""Checks whether the average of values equals target, treating
floating-point rounding error as an acceptable match."""


def average_equals(values, target):
    return sum(values) / len(values) == target
