# Source access request

Use this request for each insurer, government directory, hospital network, or healthcare directory before adding an adapter.

## Information to obtain

- Official landing-page URL and organization owner.
- Whether the hospital/doctor data is intentionally public.
- A public CSV, JSON, XML, PDF, or documented API endpoint.
- Required request method, parameters, pagination, and sample response.
- Allowed request rate, timeout, and concurrency.
- Whether automated retrieval and local storage are permitted.
- Attribution, retention, and redistribution requirements.
- Update frequency and effective/expiry date of the list.
- Stable record identifier, if supplied.
- Fields available: name, address, city, state, pincode, phone, coordinates, type, specialties, registration, doctor relationships.
- Contact or written approval for automated access if the source requires it.

## Do not request or implement

- Login or private-account access.
- CAPTCHA solving or anti-bot bypass.
- Proxy/identity rotation.
- Undocumented private APIs.
- Personal health information or patient records.

## Adapter acceptance

The source is enabled only after a sanitized fixture, parser tests, raw-response retention, field provenance, location filtering, rate limiting, and a 10–25 record review batch are complete.
