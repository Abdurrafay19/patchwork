def record_event(event, timestamp, log=[]):
    log.append((event, timestamp))
    return log