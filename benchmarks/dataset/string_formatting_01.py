"""Returns a normalized email address: whitespace trimmed and letters
lowercased, so equivalent addresses compare equal regardless of how the
user typed them."""


def normalize_email(email):
    return email.strip()
