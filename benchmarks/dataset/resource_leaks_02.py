"""Appends a line of text to a log file."""


def write_log_line(path, line):
    f = open(path, "a")
    f.write(line + "\n")
