import json

from arogio.sources import Location, build_source
from arogio.sources_osm import INDIA_STATES, OsmOverpassHospitalAdapter, resolve_state_code

JAIPUR = Location("Jaipur", "Rajasthan", "India", ("302",), False)
STATEWIDE = Location("all", "Rajasthan", "India", ("302",), True)

PAYLOAD = {
    "elements": [
        {
            "type": "node",
            "id": 123,
            "lat": 26.9124,
            "lon": 75.7873,
            "tags": {
                "amenity": "hospital",
                "name": "Sawai Man Singh Hospital",
                "name:hi": "सवाई मान सिंह अस्पताल",
                "addr:full": "JLN Marg, Jaipur",
                "addr:city": "Jaipur",
                "addr:district": "Jaipur",
                "addr:state": "Rajasthan",
                "addr:postcode": "302004",
                "phone": "+91 141 2560291; 0141-2560292",
                "email": "Info@SMS.example.org",
                "website": "sms.gov.in?utm_source=x",
                "emergency": "yes",
                "operator:type": "government",
                "healthcare:speciality": "cardiology;general",
            },
        },
        {"type": "way", "id": 9, "center": {"lat": 26.8, "lon": 75.8}, "tags": {"amenity": "hospital", "name": "Way Hospital", "addr:city": "Jaipur"}},
        {"type": "node", "id": 5, "lat": 24.5, "lon": 74.6, "tags": {"amenity": "hospital", "name": "Udaipur Clinic", "addr:city": "Udaipur"}},
        {"type": "node", "id": 6, "lat": 24.5, "lon": 74.6, "tags": {"amenity": "hospital"}},
        {"type": "node", "id": 7, "lat": 24.5, "lon": 74.6},
    ]
}


def adapter() -> OsmOverpassHospitalAdapter:
    return OsmOverpassHospitalAdapter()


def test_build_source_returns_live_adapter():
    assert isinstance(build_source("osm_overpass_health_facilities", {}), OsmOverpassHospitalAdapter)


def test_query_targets_requested_state_and_kinds():
    query = adapter().build_query("IN-RJ", ("hospital", "clinic"))
    assert '["ISO3166-2"="IN-RJ"]' in query
    assert '["amenity"="hospital"]' in query and '["amenity"="clinic"]' in query
    assert "out center tags;" in query


def test_parse_drops_untagged_elements():
    assert len(adapter().parse(json.dumps(PAYLOAD))) == 4


def test_normalization_maps_every_contact_field():
    record = adapter().normalize_source_record(PAYLOAD["elements"][0], JAIPUR)
    assert record["name"] == "Sawai Man Singh Hospital"
    assert record["name_hi"] == "सवाई मान सिंह अस्पताल"
    assert record["address"] == "JLN Marg, Jaipur"
    assert record["pincode"] == "302004"
    assert record["phone_1"] == "1412560291" and record["phone_2"] == "1412560292"
    assert record["email"] == "info@sms.example.org"
    assert record["website"] == "https://sms.gov.in"
    assert record["emergency_available"] is True
    assert record["ownership"] == "government"
    assert record["departments"] == ["Cardiology", "General"]
    assert record["license"] == "ODbL 1.0"
    assert record["source_record_id"] == "node/123"
    assert record["state"] == "Rajasthan"
    assert record["verification_status"] == "needs_review"


def test_way_geometry_uses_center():
    record = adapter().normalize_source_record(PAYLOAD["elements"][1], JAIPUR)
    assert record["latitude"] == 26.8 and record["longitude"] == 75.8


def test_ids_are_stable_and_distinct_per_osm_object():
    first = adapter().normalize_source_record(PAYLOAD["elements"][0], JAIPUR)
    again = adapter().normalize_source_record(PAYLOAD["elements"][0], JAIPUR)
    other = adapter().normalize_source_record(PAYLOAD["elements"][1], JAIPUR)
    assert first["hospital_id"] == again["hospital_id"] != other["hospital_id"]


def test_city_filter_keeps_target_and_drops_others():
    parsed = adapter().parse(PAYLOAD)
    kept = [r for r in (adapter().normalize_source_record(e, JAIPUR) for e in parsed) if adapter().filter_location(r, JAIPUR)]
    assert [r["name"] for r in kept] == ["Sawai Man Singh Hospital", "Way Hospital"]


def test_statewide_filter_still_requires_a_name():
    parsed = adapter().parse(PAYLOAD)
    kept = [r for r in (adapter().normalize_source_record(e, STATEWIDE) for e in parsed) if adapter().filter_location(r, STATEWIDE)]
    assert len(kept) == 3
    assert all(r["name"] for r in kept)


def test_plan_covers_all_states_or_one():
    assert len(adapter().discover(Location("all", "all"))) == len(INDIA_STATES) == 36
    assert adapter().discover(Location("all", "Rajasthan")) == [("IN-RJ", "Rajasthan")]


def test_state_codes_accept_name_or_iso():
    assert resolve_state_code("Tamil Nadu") == resolve_state_code("IN-TN") == "IN-TN"
    assert resolve_state_code("Atlantis") is None


def test_state_uses_authoritative_boundary_not_the_free_text_tag():
    """A misspelled addr:state must not split one state into several groups."""
    element = {"type": "node", "id": 42, "lat": 19.1, "lon": 72.9,
               "tags": {"amenity": "hospital", "name": "Typo Hospital",
                        "addr:city": "Mumbai", "addr:state": "Maharastra"}}
    record = adapter().normalize_source_record(element, Location("all", "Maharashtra", "India", (), True))
    assert record["state"] == "Maharashtra"
    assert record["source_state"] == "Maharastra"


def test_ownership_folds_free_text_operator_types():
    fold = adapter()._ownership
    assert fold("private_for_profit") == "private"
    assert fold("Private") == "private"
    assert fold("private_non_profit") == "private_not_for_profit"
    assert fold("government_facility-public") == "government"
    assert fold("public/government") == "government"
    assert fold("ngo") == "charitable"
    assert fold("community") == "community"
    assert fold(None) is None


def test_rich_tags_are_captured_and_nothing_is_dropped():
    element = {"type": "node", "id": 7, "lat": 26.9, "lon": 75.8, "tags": {
        "amenity": "hospital", "name": "Full Hospital", "name:ta": "x", "name:etymology:wikidata": "Q1",
        "facility:opd": "yes", "facility:icu": "no", "facility:ventilator": "12",
        "payment:cash": "yes", "payment:visa": "no", "fax": "+91 141 000000",
        "wikidata": "Q123", "personnel:count": "40", "description": "d", "check_date": "2025-01-01",
    }}
    record = adapter().normalize_source_record(element, JAIPUR)
    assert record["names_by_language"] == {"ta": "x"}          # etymology is not a language
    assert record["facilities"]["opd"] is True
    assert record["facilities"]["icu"] is False
    assert record["facilities"]["ventilator"] == "12"          # counts are kept, not coerced
    assert record["payment_methods"] == ["cash"]
    assert record["wikidata"] == "Q123"
    assert record["personnel_count"] == "40"
    assert record["last_checked"] == "2025-01-01"
    # Every upstream tag survives verbatim, so no mapping gap loses data.
    assert record["osm_tags"] == element["tags"]
