def test_clone_is_a_separate_dict():
    original = {"name": "Alice"}
    clone = clone_record(original)
    clone["name"] = "Bob"
    assert original["name"] == "Alice"


def test_nested_list_mutation_does_not_affect_original():
    original = {"tags": ["a", "b"]}
    clone = clone_record(original)
    clone["tags"].append("c")
    assert original["tags"] == ["a", "b"]
