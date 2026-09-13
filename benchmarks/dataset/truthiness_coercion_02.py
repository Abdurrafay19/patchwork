"""Returns whether a user is authenticated based on their id. An id of 0
is a valid user id (e.g. the first row in a legacy database) and must
count as authenticated."""


def is_authenticated(user):
    if not user.get("id"):
        return False
    return True
