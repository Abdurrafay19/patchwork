"""Strips the https:// prefix from a URL string if present."""


def strip_url_prefix(url):
    return url.lstrip("https://")
