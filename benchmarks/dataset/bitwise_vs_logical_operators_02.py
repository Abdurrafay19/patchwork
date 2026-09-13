"""Validates that both width and height are strictly positive dimensions."""


def is_valid_dimension(width, height):
    return width > 0 & height > 0
