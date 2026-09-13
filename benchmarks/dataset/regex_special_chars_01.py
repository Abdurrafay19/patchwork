"""Checks if a filename ends with the provided extension."""

import re


def matches_file_extension(filename, ext):
    return bool(re.search(f"{ext}$", filename))
