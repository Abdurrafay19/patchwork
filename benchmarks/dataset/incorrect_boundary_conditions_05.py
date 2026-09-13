"""Classifies a person's age category. Someone exactly 65 years old is
considered a senior; someone exactly 18 is considered an adult."""


def _is_senior(age):
    return age > 65


def get_age_category(age):
    if _is_senior(age):
        return "senior"
    elif age >= 18:
        return "adult"
    else:
        return "minor"
