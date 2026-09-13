"""Combines a list of student names and score values into a dict. Lists must match in length or raise ValueError."""


def combine_scores(names, scores):
    return dict(zip(names, scores))
