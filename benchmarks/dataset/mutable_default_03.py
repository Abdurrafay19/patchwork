"""Records an event with a timestamp into a log and returns the log.
Each call with no explicit log argument should produce a log containing
only that call's own events."""


def record_event(event, timestamp, log=[]):
    log.append((event, timestamp))
    return log