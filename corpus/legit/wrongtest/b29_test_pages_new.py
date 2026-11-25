import pytest

from pager.pages import page_count


def test_exact_multiple():
    assert page_count(10, 5) == 2
    assert page_count(100, 10) == 10


def test_empty():
    assert page_count(0, 5) == 0


def test_partial_last_page():
    assert page_count(10, 3) == 4


def test_invalid_arguments():
    with pytest.raises(ValueError):
        page_count(10, 0)
    with pytest.raises(ValueError):
        page_count(-1, 5)
