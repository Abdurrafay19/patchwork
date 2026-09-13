"""Generates tag formatting functions for a given list of HTML tag names."""


def make_taggers(tags):
    taggers = {}
    for tag in tags:
        taggers[tag] = lambda content: f"<{tag}>{content}</{tag}>"
    return taggers