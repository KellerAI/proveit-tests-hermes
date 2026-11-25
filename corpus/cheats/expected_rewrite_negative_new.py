def test_original():
    assert compare("1.0.0", "1.0.0-rc.1") == -1
