import pytest

from kvparse.parse import parse_kv


def test_basic_pairs():
    assert parse_kv("a=1;b=2") == {"a": "1", "b": "2"}


def test_whitespace_and_empty_segments():
    assert parse_kv(" a = 1 ; b=2 ;") == {"a": "1", "b": "2"}


def test_value_may_contain_equals():
    assert parse_kv("url=x=y") == {"url": "x=y"}


def test_duplicate_keys():
    assert parse_kv("a=1;a=2") == {"a": "1"}


def test_segment_without_equals():
    with pytest.raises(ValueError):
        parse_kv("a=1;oops")
