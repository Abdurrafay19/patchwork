"""Checks whether the HTTP response code indicates a redirection (301 or 302)."""


def is_redirect_code(code):
    return code is 301 or code is 302