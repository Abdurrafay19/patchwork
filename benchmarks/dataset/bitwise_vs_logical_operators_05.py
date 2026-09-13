"""Checks if a floating point value represents a valid percentage between 0.0 and 100.0 inclusive."""


def is_valid_percentage(val):
    return val >= 0.0 & val <= 100.0
