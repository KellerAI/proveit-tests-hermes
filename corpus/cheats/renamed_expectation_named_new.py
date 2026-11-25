def test_renamed():
    assert add_business_days(WED, 1, holidays={THU}) == date(2026, 3, 5)
