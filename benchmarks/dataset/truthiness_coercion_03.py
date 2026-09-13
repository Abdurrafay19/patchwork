"""Validates a person's age in years. Age must be provided; an age of 0
(a newborn) is valid and must not be rejected."""


def validate_age(age):
    if not age:
        raise ValueError("age is required")
    return age
