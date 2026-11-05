import pytest

@pytest.mark.xfail
def test_total():
    assert 1 + 1 == 10
