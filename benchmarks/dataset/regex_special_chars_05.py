"""Counts the occurrences of a literal keyword in text."""

import re


def count_keyword_occurrences(text, keyword):
    return len(re.findall(keyword, text))
