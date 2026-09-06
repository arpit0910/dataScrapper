from arogio.sources import Location
from arogio.sources_data_gov import DataGovHospitalAdapter


def test_data_gov_fixture_parses_and_filters_location():
    adapter = DataGovHospitalAdapter()
    rows = adapter.parse_file("tests/fixtures/data_gov_in/sample.csv")
    target = Location("Jaipur", "Rajasthan", "India")
    normalized = [adapter.normalize_source_record(row, target) for row in rows]
    assert len(rows) == 2
    assert normalized[0]["name"] == "Jaipur General Hospital"
    assert adapter.filter_location(normalized[0], target)
    assert not adapter.filter_location(normalized[1], target)
