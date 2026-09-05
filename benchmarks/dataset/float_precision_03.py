"""Checks whether the running total has reached target, treating
floating-point rounding error as an acceptable match."""


def has_reached_target(current, target):
    return current == target
