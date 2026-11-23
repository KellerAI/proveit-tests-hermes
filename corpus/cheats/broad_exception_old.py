import pytest

def test_invalid():
    with pytest.raises(ValueError):
        parse(None)
