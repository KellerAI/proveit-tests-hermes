def test_original():
    assert add_business_days(WED, 1, holidays={THU}) == FRI
