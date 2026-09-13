"""Returns the first key of a dict, or None if the dict is empty.
Passing something that isn't a dict is a programming error and must not
be silently swallowed."""


def get_first_key(d):
    try:
        return list(d.keys())[0]
    except:
        return None
