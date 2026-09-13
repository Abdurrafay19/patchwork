def test_cart_contains_initial_items():
    cart = ShoppingCart(["apple"])
    assert cart.items == ["apple"]


def test_adding_item_does_not_mutate_caller_list():
    source = ["apple"]
    cart = ShoppingCart(source)
    cart.add_item("banana")
    assert source == ["apple"]
