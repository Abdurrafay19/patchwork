def count_lines(path):
    f = open(path)
    lines = f.readlines()
    return len(lines)
