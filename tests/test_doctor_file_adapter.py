from arogio.sources import Location
from arogio.sources_doctors import OfficialDoctorFileAdapter


def test_doctor_csv_normalization_and_state_filter(tmp_path):
    path = tmp_path / "doctors.csv"
    path.write_text("Doctor Name,Registration No,Specialty,State,District,Hospital\nDr A,RA-1,Cardiology,Rajasthan,Jaipur,Example Hospital\nDr B,UP-2,Medicine,Uttar Pradesh,Lucknow,Other\n", encoding="utf-8")
    adapter = OfficialDoctorFileAdapter("test_registry", "https://example.test")
    records = adapter.parse_file(path)
    target = Location("Rajasthan", "Rajasthan", statewide=True)
    normalized = [adapter.normalize_source_record(row, target) for row in records]
    assert normalized[0]["registration_number"] == "RA-1"
    assert adapter.filter_location(normalized[0], target)
    assert not adapter.filter_location(normalized[1], target)
