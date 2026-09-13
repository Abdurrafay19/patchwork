"""Filters out occurrences of banned words from the given word list in-place."""


def filter_banned_words(words, banned):
    for word in words:
        if word in banned:
            words.remove(word)
    return words