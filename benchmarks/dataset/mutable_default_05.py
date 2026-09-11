"""A Basket holds items added to it. Each Basket instance created with
no explicit items argument should have its own independent contents,
not share a list with every other Basket instance."""


class Basket:
    def __init__(self, items=[]):
        self.items = items

    def add(self, item):
        self.items.append(item)