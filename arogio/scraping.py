from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from time import monotonic, sleep


USER_AGENT = "ArogioLocalScraper/0.1 (+local use; healthcare directory research)"


# 406 and 429 are how Overpass signals "too many requests from this client";
# both clear on their own, so they are retried rather than treated as fatal.
RETRYABLE_STATUS_CODES = {406, 429, 500, 502, 503, 504}


@dataclass
class RateLimiter:
    requests_per_minute: int = 10
    _last_request: float = 0

    def wait(self) -> None:
        interval = 60 / self.requests_per_minute
        delay = interval - (monotonic() - self._last_request)
        if delay > 0:
            sleep(delay)
        self._last_request = monotonic()


def should_retry(status_code: int | None, attempt: int, max_retries: int) -> bool:
    return attempt < max_retries and (status_code is None or status_code in RETRYABLE_STATUS_CODES)


def fetch_public_url(url: str, limiter: RateLimiter, timeout: int = 20, max_retries: int = 3) -> tuple[int, str]:
    """Fetch a normally accessible public URL with bounded retries.

    This deliberately has no proxy, browser, CAPTCHA, authentication, or anti-bot
    bypass behavior. A caller remains responsible for source approval and terms.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        limiter.wait()
        try:
            request = Request(url, headers={"User-Agent": "ArogioLocalScraper/0.1 (+local use)"})
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                return response.status, body
        except HTTPError as exc:
            last_error = exc
            if not should_retry(exc.code, attempt, max_retries):
                raise
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if not should_retry(None, attempt, max_retries):
                raise
    raise RuntimeError(f"Unable to fetch {url}: {last_error}") from last_error


def post_public_url(
    url: str,
    body: str,
    limiter: RateLimiter,
    timeout: int = 180,
    max_retries: int = 3,
    content_type: str = "application/x-www-form-urlencoded",
) -> tuple[int, str]:
    """POST to a public API endpoint with bounded retries and exponential backoff.

    Overpass and similar open endpoints require POST for long queries.  Like the
    GET helper this performs an ordinary public request only: no proxy, browser
    automation, CAPTCHA handling, authentication, or anti-bot bypass.
    """
    payload = body.encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        limiter.wait()
        try:
            request = Request(
                url,
                data=payload,
                headers={"User-Agent": USER_AGENT, "Content-Type": content_type},
                method="POST",
            )
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.status, response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            last_error = exc
            if not should_retry(exc.code, attempt, max_retries):
                raise
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if not should_retry(None, attempt, max_retries):
                raise
        # A busy open endpoint recovers on its own; back off instead of hammering it.
        sleep(min(2 ** attempt * 5, 60))
    raise RuntimeError(f"Unable to POST {url}: {last_error}") from last_error


class AllEndpointsFailedError(RuntimeError):
    """Every configured mirror rejected or failed the request."""


def post_with_failover(
    endpoints: list[str],
    body: str,
    limiter: RateLimiter,
    timeout: int = 180,
    max_retries: int = 3,
    content_type: str = "application/x-www-form-urlencoded",
    deadline: float | None = None,
) -> tuple[int, str, str]:
    """POST to the first mirror that accepts the request.

    Public API mirrors enforce a small number of concurrent slots, so a shared
    query load is spread across them.  Rotating to the next mirror is tried
    before backing off, because a busy slot on one host says nothing about the
    others.  Returns (status, body, endpoint_used).
    """
    if not endpoints:
        raise ValueError("At least one endpoint is required")
    errors: list[str] = []
    for attempt in range(max_retries + 1):
        # A caller working to a wall-clock budget must not be held past it by a
        # retry ladder against an endpoint that has gone unreachable.
        if deadline is not None and monotonic() >= deadline:
            raise AllEndpointsFailedError(f"Deadline reached before success: {', '.join(errors) or 'no attempt made'}")
        for endpoint in endpoints:
            if deadline is not None and monotonic() >= deadline:
                break
            limiter.wait()
            try:
                status, text = _post_once(endpoint, body, timeout, content_type)
                return status, text, endpoint
            except HTTPError as exc:
                errors.append(f"{endpoint}:HTTP{exc.code}")
                if exc.code not in RETRYABLE_STATUS_CODES:
                    raise
            except (URLError, TimeoutError, OSError) as exc:
                errors.append(f"{endpoint}:{type(exc).__name__}")
        sleep(min(2 ** attempt * 5, 60))
    raise AllEndpointsFailedError(f"All endpoints failed: {', '.join(errors[-len(endpoints) * 2:])}")


def _post_once(endpoint: str, body: str, timeout: int, content_type: str) -> tuple[int, str]:
    request = Request(
        endpoint,
        data=body.encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": content_type},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, response.read().decode(charset, errors="replace")
