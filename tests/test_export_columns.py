from arogio.exporters import DOCTOR_COLUMNS, HOSPITAL_COLUMNS, export_rows


def test_export_has_exact_columns(tmp_path):
    hospital_file = export_rows([], HOSPITAL_COLUMNS, tmp_path / "hospitals.xlsx")
    doctor_file = export_rows([], DOCTOR_COLUMNS, tmp_path / "doctors.csv", "csv")
    assert hospital_file.exists()
    assert doctor_file.read_text(encoding="utf-8").splitlines()[0].split(",") == DOCTOR_COLUMNS
