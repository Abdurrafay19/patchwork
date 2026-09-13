"""Maps a list of column headers to a list of row values into a dictionary. Lengths must match or raise ValueError."""


def map_headers_to_row(headers, row):
    return dict(zip(headers, row))
