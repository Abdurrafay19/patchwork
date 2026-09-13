def add_tag(tag, tags=[]):
    if tag not in tags:
        tags.append(tag)
    return tags