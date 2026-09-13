"""Calculates the dot product of two vectors. Vectors must have the same dimension or raise ValueError."""


def calculate_dot_product(vec1, vec2):
    return sum(a * b for a, b in zip(vec1, vec2))
