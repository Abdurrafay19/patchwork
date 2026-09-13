"""Creates a list of multiplier functions where each function multiplies its input by its index."""


def make_multipliers(n):
    return [lambda x: x * i for i in range(n)]