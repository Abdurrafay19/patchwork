"""Strips a standard log tag prefix '[ERROR] ' from a log line."""


def strip_log_tag(log_line):
    return log_line.lstrip("[ERROR] ")
