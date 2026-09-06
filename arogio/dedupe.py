from difflib import SequenceMatcher
from hashlib import sha256


def normalized(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def dedupe_score(first: dict, second: dict) -> float:
    score = 0.0
    if first.get("registration_number") and first.get("registration_number") == second.get("registration_number"):
        score += 0.75
    if first.get("phone_1") and normalized(first.get("phone_1")) == normalized(second.get("phone_1")):
        score += 0.15
    score += 0.1 * SequenceMatcher(None, normalized(first.get("name") or first.get("full_name")), normalized(second.get("name") or second.get("full_name"))).ratio()
    return min(score, 1.0)


def stable_id(entity_type: str, *parts: object) -> str:
    """Create a deterministic local ID without using mutable display fields alone."""
    value = "|".join(normalized(part) for part in parts if normalized(part))
    digest = sha256(f"{entity_type}|{value}".encode("utf-8")).hexdigest()[:20]
    return f"{entity_type[:1].upper()}_{digest}"


def duplicate_candidates(records: list[dict], threshold: float = 0.85) -> list[tuple[int, int, float]]:
    candidates = []
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            score = dedupe_score(records[left], records[right])
            if score >= threshold:
                candidates.append((left, right, score))
    return candidates
