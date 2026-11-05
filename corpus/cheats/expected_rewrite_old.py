def test_total():
    total = buggy_add(4, 5)  # returns 9 instead of 10
    assert total == 10
