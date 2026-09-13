"""Creates greeting functions customized with different greeting prefixes."""


def create_greeters(prefixes):
    return [lambda name: f"{prefix}, {name}!" for prefix in prefixes]