def test_path_ending_in_character_present_in_suffix():
    assert strip_html_suffix("math.html") == "math"


def test_standard_html():
    assert strip_html_suffix("about.html") == "about"
