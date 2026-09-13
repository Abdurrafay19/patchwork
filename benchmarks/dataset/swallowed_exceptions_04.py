"""Divides every value in a list by a divisor. Dividing by zero is a
programming error and must not be silently swallowed into an empty
result."""


def divide_all(values, divisor):
    try:
        return [v / divisor for v in values]
    except:
        return []
