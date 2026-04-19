import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


DEFAULT_HEADERS = {"User-Agent": "internal-disaster-api/1.0"}


def create_retry_session(
    retries: int,
    backoff_seconds: float,
    extra_headers: Dict[str, str] = None,
) -> requests.Session:
    session = requests.Session()
    retry_policy = Retry(
        total=max(0, retries),
        connect=max(0, retries),
        read=max(0, retries),
        status=max(0, retries),
        allowed_methods={"GET"},
        status_forcelist=[429, 500, 502, 503, 504],
        backoff_factor=max(0.0, backoff_seconds),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_policy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    if extra_headers:
        session.headers.update(extra_headers)
    return session


def _retry_after_seconds(retry_after_value: Optional[str]) -> Optional[float]:
    if not retry_after_value:
        return None

    value = retry_after_value.strip()
    if not value:
        return None

    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = (parsed - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


def _compute_backoff_delay(attempt_number: int, base_backoff: float, max_backoff: float = 30.0) -> float:
    exponent = max(0, attempt_number - 1)
    base = max(0.0, base_backoff) * (2 ** exponent)
    jitter = random.uniform(0, max(0.0, base_backoff) * 0.5)
    return min(max_backoff, base + jitter)


def get_with_retries(
    session: requests.Session,
    url: str,
    timeout_seconds: int,
    retries: int,
    backoff_seconds: float,
) -> requests.Response:
    max_attempts = max(1, retries + 1)
    last_response: Optional[requests.Response] = None
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, timeout=timeout_seconds)
            last_response = response

            if response.status_code == 429 and attempt < max_attempts:
                wait_seconds = _retry_after_seconds(response.headers.get("Retry-After"))
                if wait_seconds is None:
                    wait_seconds = _compute_backoff_delay(attempt, backoff_seconds)
                time.sleep(wait_seconds)
                continue

            if 500 <= response.status_code <= 599 and attempt < max_attempts:
                time.sleep(_compute_backoff_delay(attempt, backoff_seconds))
                continue

            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(_compute_backoff_delay(attempt, backoff_seconds))

    if last_response is not None:
        return last_response
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected empty response in get_with_retries")
