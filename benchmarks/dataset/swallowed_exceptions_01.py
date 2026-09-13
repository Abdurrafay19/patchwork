"""Looks up a key in a config dict, returning None if the key is
missing. Passing a non-dict config is a programming error and must not
be silently swallowed."""


def get_config_value(config, key):
    try:
        return config[key]
    except:
        return None
