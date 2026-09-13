def test_message_starting_with_letters_in_tag():
    assert strip_log_tag("[ERROR] Read timed out") == "Read timed out"


def test_standard_error_message():
    assert strip_log_tag("[ERROR] Disk full") == "Disk full"
