"""Checks whether the transaction status represents a successful outcome."""


def is_successful_status(status):
    return status is "COMPLETED"