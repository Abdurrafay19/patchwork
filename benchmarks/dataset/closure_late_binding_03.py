"""Returns a dictionary of validator functions, one for each required field name."""


def create_field_validators(fields):
    validators = {}
    for field in fields:
        validators[field] = lambda data: field in data and data[field] is not None
    return validators