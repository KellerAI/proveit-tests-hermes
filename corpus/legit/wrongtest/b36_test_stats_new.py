import pytest

from midstat.stats import median


def test_odd_count():
    assert median([3, 1, 2]) == 2
    assert median([5]) == 5


def test_odd_count_unsorted():
    assert median([9, 1, 5, 3, 7]) == 5


def test_even_count():
    assert median([1, 2, 3, 4]) == 2.5


def test_empty_raises():
    with pytest.raises(ValueError):
        median([])


def test_input_not_mutated():
    data = [3, 1, 2]
    median(data)
    assert data == [3, 1, 2]
