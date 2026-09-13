def write_log_line(path, line):
    f = open(path, "a")
    f.write(line + "\n")
