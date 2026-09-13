def test_taggers_format_correctly():
    taggers = make_taggers(["b", "i", "p"])
    assert taggers["b"]("bold") == "<b>bold</b>"
    assert taggers["i"]("italic") == "<i>italic</i>"
    assert taggers["p"]("para") == "<p>para</p>"