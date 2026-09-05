"""Returns the number of lines in a text file."""


def count_lines(path):
    f = open(path)
    lines = f.readlines()
    return len(lines)
