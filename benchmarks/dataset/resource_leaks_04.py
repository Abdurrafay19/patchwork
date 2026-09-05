"""Reads a text file and returns its lines with surrounding whitespace
stripped."""


def read_stripped_lines(path):
    f = open(path)
    return [line.strip() for line in f]
