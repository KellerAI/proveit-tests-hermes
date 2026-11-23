import pytest

def test_invalid():
    with pytest.raises(Exception):
        parse(None)
