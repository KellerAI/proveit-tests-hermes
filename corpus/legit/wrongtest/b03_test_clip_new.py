import pytest

from clipstr.clip import truncate


def test_short_text_unchanged():
    assert truncate("hi", 5) == "hi"


def test_exact_fit_unchanged():
    assert truncate("hello", 5) == "hello"


def test_long_text_is_clipped():
    assert truncate("hello world", 8) == "hello w\u2026"


def test_width_too_small():
    with pytest.raises(ValueError):
        truncate("hello", 0)
