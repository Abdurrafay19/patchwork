"""Returns the items belonging to the given 0-indexed page, where each
page holds page_size items."""


def get_page_items(items, page, page_size):
    start = page * page_size
    return items[start : start + page_size - 1]
