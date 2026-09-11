"""Returns the user's email address from their profile, or None if the
profile is missing or has no email set."""


def get_user_email(user):
    return user["profile"]["email"]
