"""Removes a given file extension from the end of a filename."""


def strip_file_extension(filename, ext):
    return filename.rstrip(ext)
