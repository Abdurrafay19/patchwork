def test_validators_check_correct_field():
    validators = create_field_validators(["name", "email"])
    assert validators["name"]({"name": "Alice"}) is True
    assert validators["name"]({"email": "a@b.com"}) is False