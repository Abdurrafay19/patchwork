"""Checks if an email matches the specified domain exactly."""

import re


def is_matching_domain(email, domain):
    return bool(re.search(f"@{domain}$", email))
