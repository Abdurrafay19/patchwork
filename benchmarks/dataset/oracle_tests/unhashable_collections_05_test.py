def test_unique_payloads():
    payloads = [{"action": "click"}, {"action": "scroll"}, {"action": "click"}]
    result = deduplicate_payloads(payloads)
    assert len(result) == 2
    assert {"action": "click"} in result
