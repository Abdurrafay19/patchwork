"""Appends an item to a running list and returns it. Each call with no
explicit target_list should start a fresh empty list -- calls must not
leak state into each other."""


def append_item(item, target_list=[]):
    target_list.append(item)
    return target_list