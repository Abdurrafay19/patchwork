def test_deduplicates_dicts():
    records = [{"id": 1}, {"id": 2}, {"id": 1}]
    result = get_unique_records(records)
    assert len(result) == 2
    assert {"id": 1} in result
    assert {"id": 2} in result
