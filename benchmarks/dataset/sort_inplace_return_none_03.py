"""Returns a list of user dictionaries sorted by their age in ascending order."""


def sort_users_by_age(users):
    return users.sort(key=lambda u: u["age"])
