"""Returns the configured UI theme name, or None if not set anywhere
in the config."""


def get_theme(config):
    return config["app"]["settings"]["theme"]
