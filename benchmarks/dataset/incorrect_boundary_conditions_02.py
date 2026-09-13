"""Validates that a password meets the minimum required length of 8
characters. A password of exactly 8 characters is valid."""


def _meets_min_length(password, min_length):
    return len(password) > min_length


def validate_password(password):
    if not _meets_min_length(password, 8):
        raise ValueError("password too short")
    return True
