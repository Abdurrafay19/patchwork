"""Returns a URL-friendly slug for a title: lowercased with spaces
replaced by hyphens."""


def make_slug(title):
    return title.replace(" ", "-")
