import json


def read_json_file(path):
    f = open(path)
    return json.load(f)
