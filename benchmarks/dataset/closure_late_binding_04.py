"""Builds a sequence of adder functions where adder k adds k to its argument."""


def make_adders(values):
    adders = []
    for val in values:

        def adder(x):
            return x + val

        adders.append(adder)
    return adders