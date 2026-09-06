from arogio.exporters import DOCTOR_COLUMNS, HOSPITAL_COLUMNS, export_rows


def test_export_has_exact_columns(tmp_path):
    hospital_file = export_rows([], HOSPITAL_COLUMNS, tmp_path / "hospitals.xlsx")
    doctor_file = export_rows([], DOCTOR_COLUMNS, tmp_path / "doctors.csv", "csv")
    assert hospital_file.exists()
    assert doctor_file.read_text(encoding="utf-8").splitlines()[0].split(",") == DOCTOR_COLUMNS


def test_list_and_dict_values_export_without_crashing(tmp_path):
    """Canonical rows carry list fields; openpyxl rejects those unflattened."""
    from arogio.exporters import export_rows
    rows = [{"name": "A", "departments": ["Cardiology", "General"], "extra": {"k": "v"}}]
    columns = ["name", "departments", "extra"]
    for fmt in ("xlsx", "csv", "json"):
        out = export_rows(rows, columns, tmp_path / f"out.{fmt}", fmt)
        assert out.exists() and out.stat().st_size > 0
    text = (tmp_path / "out.csv").read_text(encoding="utf-8")
    assert "Cardiology; General" in text
