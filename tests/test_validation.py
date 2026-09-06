from arogio.validation import is_within_target_location, validate_coordinates, validate_record


def test_validation_rejects_bad_critical_fields():
    errors = validate_record({"name": "Clinic", "pincode": "123", "email": "bad"}, ["name", "address"])
    assert set(errors) == {"address", "pincode", "email"}


def test_location_is_configuration_driven():
    location = {"city": "Jaipur", "state": "Rajasthan"}
    assert is_within_target_location({"city": "jaipur", "state": "RAJASTHAN"}, location)
    assert not is_within_target_location({"city": "Jodhpur", "state": "Rajasthan"}, location)


def test_coordinate_ranges():
    assert validate_coordinates(26.9, 75.8)
    assert not validate_coordinates(200, 75.8)
