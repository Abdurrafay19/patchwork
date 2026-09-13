"""Strips a domain suffix (.com) from a domain name string."""


def strip_domain_suffix(domain):
    return domain.rstrip(".com")
