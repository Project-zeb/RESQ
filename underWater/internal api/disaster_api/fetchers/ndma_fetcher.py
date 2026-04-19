import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from disaster_api.fetchers.http_client import create_retry_session, get_with_retries


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", maxsplit=1)[-1]
    return tag


def _rss_item_links(xml_bytes: bytes, base_url: str) -> list[str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    if _local_name(root.tag) != "rss":
        return []

    links: list[str] = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        for child in list(item):
            if _local_name(child.tag) != "link":
                continue
            text = (child.text or "").strip()
            if not text:
                continue
            links.append(urljoin(base_url, text))
            break
    return links


def _rss_items(xml_bytes: bytes, base_url: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    if _local_name(root.tag) != "rss":
        return []

    items: list[dict[str, str]] = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue

        row = {
            "guid": "",
            "title": "",
            "category": "",
            "pub_date": "",
            "link": "",
        }

        for child in list(item):
            name = _local_name(child.tag)
            text = (child.text or "").strip()
            if name == "guid":
                row["guid"] = text
            elif name == "title":
                row["title"] = text
            elif name == "category":
                row["category"] = text
            elif name == "pubDate":
                row["pub_date"] = text
            elif name == "link":
                row["link"] = urljoin(base_url, text) if text else ""

        if not row["guid"]:
            row["guid"] = row["link"] or row["title"]
        if not row["title"]:
            row["title"] = "NDMA alert"
        items.append(row)
    return items


def _is_cap_alert(xml_bytes: bytes) -> bool:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return False
    return _local_name(root.tag) == "alert"


def _merge_cap_alert_documents(documents: list[bytes]) -> bytes:
    payload = [b"<alerts>"]
    for doc in documents:
        cleaned = re.sub(br"^\s*<\?xml[^>]*\?>", b"", doc).strip()
        if cleaned:
            payload.append(cleaned)
    payload.append(b"</alerts>")
    return b"".join(payload)


def _to_iso_utc(date_text: str) -> str:
    text = (date_text or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return ""


def _escape_xml(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _rss_items_to_alert_xml(items: list[dict[str, str]]) -> bytes:
    blocks = ["<alerts>"]
    for item in items:
        guid = _escape_xml(item.get("guid", ""))
        title = _escape_xml(item.get("title", "NDMA alert"))
        category = _escape_xml(item.get("category", "Met") or "Met")
        sent = _escape_xml(_to_iso_utc(item.get("pub_date", "")))
        link = _escape_xml(item.get("link", ""))

        block = (
            "<alert>"
            f"<identifier>{guid}</identifier>"
            "<sender>NDMA SACHET RSS</sender>"
            f"<sent>{sent}</sent>"
            "<status>Actual</status>"
            "<msgType>Alert</msgType>"
            "<scope>Public</scope>"
            "<info>"
            "<language>en-IN</language>"
            f"<category>{category}</category>"
            f"<event>{title}</event>"
            "<urgency>Unknown</urgency>"
            "<severity>Unknown</severity>"
            "<certainty>Possible</certainty>"
            f"<headline>{title}</headline>"
            f"<description>{title}</description>"
            "<area><areaDesc>India</areaDesc></area>"
            f"<web>{link}</web>"
            "</info>"
            "</alert>"
        )
        blocks.append(block)
    blocks.append("</alerts>")
    return "".join(blocks).encode("utf-8")


def fetch_ndma_cap_feed(
    url: str,
    timeout_seconds: int,
    retries: int = 2,
    backoff_seconds: float = 0.5,
    rss_item_limit: int = 20,
) -> bytes:
    session = create_retry_session(retries=retries, backoff_seconds=backoff_seconds)
    try:
        response = get_with_retries(
            session=session,
            url=url,
            timeout_seconds=timeout_seconds,
            retries=retries,
            backoff_seconds=backoff_seconds,
        )
        response.raise_for_status()
        payload = response.content

        rss_items = _rss_items(payload, base_url=url)
        if rss_items:
            limited = rss_items[: max(1, rss_item_limit)]
            return _rss_items_to_alert_xml(limited)

        item_links = _rss_item_links(payload, base_url=url)
        if not item_links:
            return payload

        cap_documents: list[bytes] = []
        for link in item_links[: min(max(1, rss_item_limit), 5)]:
            try:
                detail_response = get_with_retries(
                    session=session,
                    url=link,
                    timeout_seconds=max(2, min(timeout_seconds, 4)),
                    retries=0,
                    backoff_seconds=backoff_seconds,
                )
                detail_response.raise_for_status()
            except Exception:
                continue

            detail_payload = detail_response.content
            if _is_cap_alert(detail_payload):
                cap_documents.append(detail_payload)

        if cap_documents:
            return _merge_cap_alert_documents(cap_documents)

        return payload
    finally:
        session.close()
