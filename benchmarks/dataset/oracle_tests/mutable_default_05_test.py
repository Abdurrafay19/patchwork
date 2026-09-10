def test_new_basket_starts_empty():
    basket = Basket()
    assert basket.items == []


def test_two_baskets_do_not_share_items():
    basket_a = Basket()
    basket_a.add("apple")
    basket_b = Basket()
    assert basket_b.items == []
