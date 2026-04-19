from typing import Any, Dict, List

from disaster_api.fetchers.http_client import create_retry_session, get_with_retries


def fetch_ogd_records(
    url: str,
    timeout_seconds: int,
    api_key: str = "",
    retries: int = 2,
    backoff_seconds: float = 0.5,
) -> List[Dict[str, Any]]:
    if not url:
        return []

    headers: Dict[str, str] = {}
    if api_key:
        headers["api-key"] = api_key

    session = create_retry_session(retries=retries, backoff_seconds=backoff_seconds, extra_headers=headers)
    try:
        response = get_with_retries(
            session=session,
            url=url,
            timeout_seconds=timeout_seconds,
            retries=retries,
            backoff_seconds=backoff_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        session.close()

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    candidates = []
    if isinstance(payload.get("records"), list):
        candidates = payload["records"]
    elif isinstance(payload.get("result"), dict) and isinstance(
        payload["result"].get("records"), list
    ):
        candidates = payload["result"]["records"]
    elif isinstance(payload.get("data"), list):
        candidates = payload["data"]

    return [item for item in candidates if isinstance(item, dict)]
