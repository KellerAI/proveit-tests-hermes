import pytest

from retrywait.backoff import backoff


def test_first_attempt():
    assert backoff(0) == 0.5


def test_exponential_growth():
    assert backoff(3) == 4.0


def test_capped():
    assert backoff(10) == 30.0


def test_non_int_attempt():
    with pytest.raises(TypeError):
        backoff("1")


def test_negative_attempt():
    with pytest.raises(ValueError):
        backoff(-1)
