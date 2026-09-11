"""Reads and parses a JSON file, returning the resulting object."""

import json


def read_json_file(path):
    f = open(path)
    return json.load(f)
