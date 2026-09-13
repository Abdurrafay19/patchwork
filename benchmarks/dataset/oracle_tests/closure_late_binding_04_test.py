def test_each_adder_uses_its_own_value():
    adders = make_adders([10, 20, 30])
    results = [fn(5) for fn in adders]
    assert results == [15, 25, 35]