"""Truncates text to at most max_length characters, appending an
ellipsis only when truncation actually occurs."""


def truncate_with_ellipsis(text, max_length):
    return text[:max_length] + "..."
