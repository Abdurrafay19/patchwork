"""Checks if a given integer is both greater than 0 and evenly divisible by 2."""


def is_even_and_positive(num):
    return num > 0 & num % 2 == 0
