from typing import Any, Dict, List

from disaster_api.fetchers.http_client import create_retry_session, get_with_retries


def fetch_mosdac_records(
    url: str,
    timeout_seconds: int,
    api_token: str = "",
    retries: int = 2,
    backoff_seconds: float = 0.5,
) -> List[Dict[str, Any]]:
    if not url:
        return []

    headers: Dict[str, str] = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

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
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" not in content_type:
            return []

        payload: Any = response.json()
    finally:
        session.close()

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("records"), list):
            return [item for item in payload["records"] if isinstance(item, dict)]
        if isinstance(payload.get("data"), list):
            return [item for item in payload["data"] if isinstance(item, dict)]
    return []
