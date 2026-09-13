"""Returns a deduplicated list of records preserving uniqueness by dictionary contents."""


def get_unique_records(records):
    return list(set(records))
