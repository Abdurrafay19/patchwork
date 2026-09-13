"""Checks whether access is permitted if the user is either an admin or the resource owner."""


def is_accessible(is_admin, is_owner):
    return is_admin | is_owner == True
