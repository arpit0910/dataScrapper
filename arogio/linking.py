"""Conservative matching for doctor/hospital relationships."""

from difflib import SequenceMatcher

from .dedupe import normalized, stable_id


def _tokens(value: str | None) -> set[str]:
    return {token for token in normalized(value).replace("(", " ").replace(")", " ").split() if len(token) > 1}


_GENERIC = {"hospital", "hospitals", "multispeciality", "multispecialty", "research", "centre", "center", "private", "limited", "pvt", "ltd"}


def match_hospital(doctor: dict, hospitals: list[dict]) -> dict | None:
    organization = doctor.get("organization_name") or doctor.get("hospital_name")
    if not organization:
        return None
    org = normalized(organization)
    doctor_city = (doctor.get("city") or "").casefold()
    doctor_state = (doctor.get("state") or "").casefold()
    candidates = [hospital for hospital in hospitals if (hospital.get("state") or "").casefold() == doctor_state and (hospital.get("city") or "").casefold() in {doctor_city, doctor_state}]
    city_candidates = [hospital for hospital in candidates if (hospital.get("city") or "").casefold() == doctor_city]
    if city_candidates:
        candidates = city_candidates
    exact = [hospital for hospital in candidates if org in {normalized(hospital.get("name")), normalized(hospital.get("name_en"))}]
    if len(exact) == 1:
        return exact[0]
    distinctive = _tokens(organization) - _GENERIC
    distinctive_hits = [hospital for hospital in candidates if len(distinctive & (_tokens(hospital.get("name")) - _GENERIC)) >= (2 if len(distinctive) >= 2 else 1)]
    if len(distinctive_hits) == 1:
        return distinctive_hits[0]
    scored: list[tuple[float, dict]] = []
    org_tokens = _tokens(organization)
    for hospital in candidates:
        name = hospital.get("name") or hospital.get("name_en") or ""
        name_tokens = _tokens(name)
        overlap = len(org_tokens & name_tokens)
        if overlap < 2:
            continue
        score = max(SequenceMatcher(None, org, normalized(name)).ratio(), overlap / max(1, min(len(org_tokens), len(name_tokens))))
        if score >= 0.50:
            scored.append((score, hospital))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or (len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05):
        return None
    return scored[0][1]


def link_payload(doctor: dict, hospital: dict | None) -> dict:
    hospital_name = (hospital or {}).get("name") or doctor.get("organization_name") or ""
    hospital_city = (hospital or {}).get("city") or doctor.get("city") or ""
    hospital_id = (hospital or {}).get("hospital_id")
    return {"doctor_hospital_link_id": stable_id("link", doctor.get("doctor_id"), hospital_id or hospital_name, hospital_city), "doctor_id": doctor.get("doctor_id"), "hospital_id": hospital_id, "hospital_name": hospital_name, "hospital_city": hospital_city, "doctor_hospital_role": "practices_at", "relationship_source_url": doctor.get("source_url", ""), "relationship_last_verified_at": None}
