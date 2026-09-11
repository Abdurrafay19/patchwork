"""Adds a tag to a collection of tags and returns the collection. Each
call with no explicit tags argument should start from an empty
collection, independent of any previous call."""


def add_tag(tag, tags=[]):
    if tag not in tags:
        tags.append(tag)
    return tags