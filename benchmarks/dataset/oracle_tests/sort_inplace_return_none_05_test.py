def test_ranked_items_order():
    assert get_ranked_items(["gold", "bronze", "silver"]) == [
        "bronze",
        "gold",
        "silver",
    ]
