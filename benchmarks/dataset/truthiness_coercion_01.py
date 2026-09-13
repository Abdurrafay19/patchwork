"""Returns the configured page size, or 10 if not set. A page_size of 0
(meaning "show all") is a valid, distinct configured value."""


def get_page_size(config):
    return config.get("page_size") or 10
