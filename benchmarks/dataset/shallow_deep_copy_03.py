"""A ShoppingCart holds a list of item names. Constructing a cart from
an existing list must not alias that list -- later changes to the cart
must not leak back into the caller's original list."""


class ShoppingCart:
    def __init__(self, items):
        self.items = items

    def add_item(self, item):
        self.items.append(item)
