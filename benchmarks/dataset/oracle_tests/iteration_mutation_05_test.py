def test_removes_consecutive_zero_items():
    cart = [
        {"name": "A", "quantity": 0},
        {"name": "B", "quantity": 0},
        {"name": "C", "quantity": 2},
    ]
    assert remove_out_of_stock(cart) == [{"name": "C", "quantity": 2}]