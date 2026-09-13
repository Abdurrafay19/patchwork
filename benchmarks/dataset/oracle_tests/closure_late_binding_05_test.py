def test_greeters_retain_prefix():
    greeters = create_greeters(["Hello", "Hi", "Welcome"])
    assert greeters[0]("World") == "Hello, World!"
    assert greeters[1]("World") == "Hi, World!"
    assert greeters[2]("World") == "Welcome, World!"