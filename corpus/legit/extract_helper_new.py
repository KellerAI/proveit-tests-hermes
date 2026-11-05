def _check_total(total):
    assert total == 2
    assert total > 0

def test_total():
    total = add(1, 1)
    _check_total(total)
