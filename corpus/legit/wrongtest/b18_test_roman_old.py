import pytest

from romanum.roman import to_roman


def test_small_additive_values():
    assert to_roman(1) == "I"
    assert to_roman(3) == "III"
    assert to_roman(8) == "VIII"


def test_tens_and_thousands():
    assert to_roman(30) == "XXX"
    assert to_roman(2000) == "MM"


def test_four():
    assert to_roman(4) == "IIII"


def test_out_of_range():
    with pytest.raises(ValueError):
        to_roman(0)
    with pytest.raises(ValueError):
        to_roman(4000)
