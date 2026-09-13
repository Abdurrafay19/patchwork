def test_dynamically_loaded_version():
    loaded_version = "version_2"[0] + "version_2"[-1]
    assert is_supported_version(loaded_version) is True


def test_unsupported_version():
    assert is_supported_version("v1") is False