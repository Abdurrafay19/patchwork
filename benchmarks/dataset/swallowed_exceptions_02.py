"""Returns the first positive number in an iterable, or None if there
isn't one. Passing something that isn't iterable is a programming error
and must not be silently swallowed."""


def get_first_positive(numbers):
    try:
        return next(n for n in numbers if n > 0)
    except:
        return None
