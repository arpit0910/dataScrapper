import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def normalize_name(value: str | None) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    return value.title()


def normalize_gender(value: str | None) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    values = {"male": "male", "m": "male", "female": "female", "f": "female", "other": "other"}
    return values.get(value.casefold())


def normalize_email(value: str | None) -> str | None:
    value = clean_text(value)
    if not value or "@" not in value or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
        return None
    if any(token in value.casefold() for token in ("example.com", "test.com", "placeholder")):
        return None
    return value.casefold()


def normalize_phone(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "+91", digits
    if len(digits) == 10:
        # Indian fixed-line numbers may be a 10-digit area-code + subscriber
        # number after the domestic trunk prefix has been removed.
        return "+91", digits
    # Retain plausible Indian landlines without pretending they are mobile numbers.
    if len(digits) in (7, 8, 11):
        return "+91", digits
    return None, None


def normalize_url(value: str | None) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parts = urlsplit(value)
    if not parts.netloc or "." not in parts.netloc:
        return None
    query = [(key, val) for key, val in parse_qsl(parts.query) if not key.casefold().startswith(("utm_", "fbclid"))]
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), urlencode(query), ""))


def normalize_pincode(value: str | None) -> str | None:
    value = clean_text(value)
    return value if value and re.fullmatch(r"\d{6}", value) else None


def normalize_coordinate(value: object, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


def normalize_address(value: str | None) -> str | None:
    return clean_text(value)
