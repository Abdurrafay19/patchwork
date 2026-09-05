"""Returns a product's price amount, or None if pricing info is
missing."""


def get_product_price(product):
    return product["pricing"]["amount"]
