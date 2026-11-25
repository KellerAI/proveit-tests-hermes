def test_renamed():
    assert compare("1.0.0", "1.0.0-rc.1") == -1
