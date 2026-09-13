"""Checks whether a string begins with a bracketed version tag like '[v1]'."""

import re


def starts_with_tag(text, tag):
    return bool(re.match(f"^{tag}", text))
