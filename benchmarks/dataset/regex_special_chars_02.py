"""Checks if a text string contains the exact mathematical or literal subpattern."""

import re


def contains_exact_subpattern(text, sub):
    return bool(re.search(sub, text))
