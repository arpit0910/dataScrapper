from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from time import monotonic, sleep


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
