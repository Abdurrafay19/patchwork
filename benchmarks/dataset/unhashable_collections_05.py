"""Filters out duplicate payload dicts from a message queue list."""


def deduplicate_payloads(payloads):
    return list(set(payloads))
