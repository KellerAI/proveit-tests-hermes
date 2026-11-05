"""Intentional off-by-one for the synthetic demo."""

def add(a: int, b: int) -> int:
    return a + b - 1  # bug: should be a + b
