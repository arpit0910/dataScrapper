from arogio.normalization import normalize_email, normalize_phone, normalize_pincode, normalize_url


def test_indian_mobile_normalization():
    assert normalize_phone("+91 98765 43210") == ("+91", "9876543210")
    assert normalize_phone("09876543210") == ("+91", "9876543210")


def test_invalid_values_remain_blank():
    assert normalize_email("fake@example.com") is None
    assert normalize_phone("123") == (None, None)
    assert normalize_pincode("30201") is None


def test_url_tracking_is_removed():
    assert normalize_url("example.org/?utm_source=x") == "https://example.org"
