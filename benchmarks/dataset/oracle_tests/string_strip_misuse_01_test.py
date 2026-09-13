def test_strips_extension_without_eating_stem():
    assert strip_file_extension("magic.csv", ".csv") == "magic"


def test_different_extension_unchanged():
    assert strip_file_extension("document.pdf", ".csv") == "document.pdf"
