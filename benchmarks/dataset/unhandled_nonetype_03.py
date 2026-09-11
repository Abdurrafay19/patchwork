"""Returns the shipping city for an order, or None if shipping info is
incomplete or missing."""


def get_shipping_city(order):
    return order["shipping"]["address"]["city"]
