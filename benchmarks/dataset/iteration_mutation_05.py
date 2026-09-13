"""Removes all items from a shopping cart list whose quantity is zero or negative."""


def remove_out_of_stock(cart):
    for item in cart:
        if item.get("quantity", 0) <= 0:
            cart.remove(item)
    return cart