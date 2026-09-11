from arogio.cli import _resume_ids


def test_resume_retries_failed_missing_or_different_model():
    rows = [
        {"hospital_id": "done", "source": "osm", "local_ai_extraction": {"status": "needs_review", "model": "local"}},
        {"hospital_id": "failed", "source": "osm", "local_ai_extraction": {"status": "failed", "model": "local"}},
        {"hospital_id": "missing", "source": "osm"},
        {"hospital_id": "other_model", "source": "osm", "local_ai_extraction": {"status": "needs_review", "model": "other"}},
        {"hospital_id": "other_source", "source": "other"},
    ]
    assert _resume_ids(rows, "osm", "local") == {"done"}
    assert _resume_ids(rows, "osm", None) == {"done", "failed", "missing", "other_model"}
