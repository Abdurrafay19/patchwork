"""Checks whether a given page number is within the valid range for a
paginated list. Valid pages run from 0 up to (but not including)
total_pages."""


def _total_pages(item_count, page_size):
    return (item_count + page_size - 1) // page_size


def is_valid_page(page, item_count, page_size):
    total = _total_pages(item_count, page_size)
    return 0 <= page <= total
