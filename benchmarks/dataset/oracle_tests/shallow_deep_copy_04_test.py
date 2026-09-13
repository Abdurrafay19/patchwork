def test_merge_includes_both_sources():
    base = {"db": {"host": "localhost"}}
    extra = {"debug": True}
    merged = merge_configs(base, extra)
    assert merged["debug"] is True
    assert merged["db"]["host"] == "localhost"


def test_mutating_merged_nested_value_does_not_affect_base():
    base = {"db": {"host": "localhost"}}
    extra = {"debug": True}
    merged = merge_configs(base, extra)
    merged["db"]["host"] = "remote"
    assert base["db"]["host"] == "localhost"
