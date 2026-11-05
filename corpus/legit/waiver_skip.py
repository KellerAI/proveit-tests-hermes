import pytest

@pytest.mark.skip(reason="flaky upstream")
def test_flaky_network():
    # proveit: intended waiting on upstream issue #42
    assert fetch() == 1
