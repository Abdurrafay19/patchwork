def get_page_items(items, page, page_size):
    start = page * page_size
    return items[start : start + page_size - 1]
