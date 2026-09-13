def increment_count(key, counts={}):
    counts[key] = counts.get(key, 0) + 1
    return counts