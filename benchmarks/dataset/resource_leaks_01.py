"""Reads and returns the full contents of a text file."""


def read_file_contents(path):
    f = open(path)
    return f.read()
