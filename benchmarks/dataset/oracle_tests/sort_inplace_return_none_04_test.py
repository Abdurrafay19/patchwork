def test_sorts_transactions():
    txs = [{"amount": 10.5}, {"amount": 99.0}, {"amount": 5.0}]
    assert sort_transactions_by_amount(txs) == [
        {"amount": 99.0},
        {"amount": 10.5},
        {"amount": 5.0},
    ]
