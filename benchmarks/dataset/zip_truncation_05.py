"""Counts matching answers between user submissions and answer key. Lists must be equal length or raise ValueError."""


def check_matching_answers(user_answers, key):
    return sum(1 for u, k in zip(user_answers, key) if u == k)
