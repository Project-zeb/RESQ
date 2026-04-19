import hashlib
import json
import logging
import os
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from disaster_api import db
from disaster_api.config import Settings
from disaster_api.fetchers.mosdac_fetcher import fetch_mosdac_records
from disaster_api.fetchers.ndma_fetcher import fetch_ndma_cap_feed
from disaster_api.fetchers.ogd_fetcher import fetch_ogd_records
from disaster_api.models.alert_model import Alert
from disaster_api.parsers.cap_parser import parse_cap_alerts


LOGGER = logging.getLogger(__name__)
_IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _to_utc_iso(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None

    iso_candidate = text
    if iso_candidate.endswith("Z"):
        iso_candidate = f"{iso_candidate[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        pass

    for fmt, tzinfo in (
        ("%a %b %d %H:%M:%S IST %Y", _IST_TZ),
        ("%a %b %d %H:%M IST %Y", _IST_TZ),
    ):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=tzinfo)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            continue

    return text


def _pick(record: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _stable_external_id(record: Dict[str, Any], prefix: str) -> str:
    raw = json.dumps(record, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()}"


def _normalize_records(records: Iterable[Dict[str, Any]], source_name: str) -> List[Alert]:
    normalized: List[Alert] = []

    for record in records:
        external_id = _pick(record, "id", "_id", "identifier", "record_id")
        if not external_id:
            external_id = _stable_external_id(record, source_name)

        effective_at = _pick(
            record,
            "effective_at",
            "effective_start_time",
            "onset",
            "start_time",
            "start_date",
        )
        issued_at = _pick(
            record,
            "issued_at",
            "issue_date",
            "observation_time",
            "timestamp",
            "date",
            "created_at",
        ) or effective_at
        expires_at = _pick(record, "expires_at", "valid_till", "end_date", "effective_end_time", "end_time")

        normalized.append(
            Alert(
                source=source_name,
                external_id=external_id,
                event_type=_pick(record, "event", "event_type", "category", "disaster_type", "type"),
                severity=_pick(record, "severity", "alert_level", "risk_level"),
                area=_pick(record, "area", "district", "state", "location", "area_desc"),
                issued_at=_to_utc_iso(issued_at),
                effective_at=_to_utc_iso(effective_at),
                expires_at=_to_utc_iso(expires_at),
                headline=_pick(record, "headline", "title", "name"),
                description=_pick(record, "description", "summary", "details", "warning_message", "message"),
                payload=record,
            )
        )

    return normalized


def _collector_records_from_snapshot(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}

    merged: List[Dict[str, Any]] = []
    seen = set()

    def _add(record: Dict[str, Any], section: str) -> None:
        if not isinstance(record, dict):
            return
        candidate = dict(record)
        candidate["source_section"] = section
        fingerprint = "|".join(
            [
                str(candidate.get("identifier", "")).strip(),
                str(candidate.get("disaster_type", "")).strip().lower(),
                str(candidate.get("effective_start_time", "")).strip(),
                str(candidate.get("area_description", "")).strip().lower(),
            ]
        )
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        merged.append(candidate)

    for item in (raw.get("alerts") or []):
        _add(item, "alerts")

    for item in ((raw.get("nowcast") or {}).get("nowcastDetails") or []):
        if not isinstance(item, dict):
            continue
        location_data = item.get("location") if isinstance(item.get("location"), dict) else {}
        lat_value = location_data.get("lat", location_data.get("latitude"))
        lon_value = location_data.get("lon", location_data.get("longitude"))
        coordinates = location_data.get("coordinates")
        if (lat_value is None or lon_value is None) and isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
            lon_value = coordinates[0]
            lat_value = coordinates[1]

        centroid = ""
        try:
            if lat_value is not None and lon_value is not None:
                centroid = f"{float(lon_value)},{float(lat_value)}"
        except (TypeError, ValueError):
            centroid = ""

        events_value = item.get("events")
        if isinstance(events_value, list):
            events_blob = ", ".join([str(entry.get("event") if isinstance(entry, dict) else entry) for entry in events_value])
        else:
            events_blob = "" if events_value is None else str(events_value)

        display_type = item.get("event_category") or item.get("disaster_type") or "Nowcast"
        first_event = events_blob.split(",")[0].strip() if events_blob else ""
        if str(display_type).strip().lower() == "rain" and first_event:
            display_type = first_event

        _add(
            {
                "identifier": item.get("identifier") or f"nowcast-{item.get('effective_start_time', '')}-{item.get('area_description', '')}",
                "disaster_type": display_type,
                "severity": str(item.get("severity", "WATCH")).upper(),
                "area_description": item.get("area_description") or location_data.get("district") or location_data.get("state") or "",
                "warning_message": events_blob,
                "effective_start_time": item.get("effective_start_time") or item.get("entry_time"),
                "effective_end_time": item.get("effective_end_time"),
                "alert_source": item.get("source") or "SACHET Nowcast",
                "severity_color": item.get("severity_color", "yellow"),
                "centroid": centroid,
            },
            "nowcast",
        )

    for item in ((raw.get("earthquakes") or {}).get("alerts") or []):
        if not isinstance(item, dict):
            continue
        lat_value = item.get("latitude")
        lon_value = item.get("longitude")
        centroid = ""
        try:
            if lat_value is not None and lon_value is not None:
                centroid = f"{float(lon_value)},{float(lat_value)}"
        except (TypeError, ValueError):
            centroid = ""

        _add(
            {
                "identifier": item.get("identifier") or f"eq-{item.get('effective_start_time', '')}-{item.get('latitude', '')}-{item.get('longitude', '')}",
                "disaster_type": item.get("disaster_type") or "Earthquake",
                "severity": item.get("severity") or "ALERT",
                "area_description": item.get("direction") or item.get("location") or "Earthquake Region",
                "warning_message": item.get("warning_message") or "",
                "effective_start_time": item.get("effective_start_time"),
                "effective_end_time": item.get("effective_end_time"),
                "alert_source": item.get("source") or "SACHET Earthquake",
                "severity_color": item.get("severity_color", "orange"),
                "centroid": centroid,
            },
            "earthquakes",
        )

    for item in ((raw.get("location_alerts") or {}).get("alerts") or []):
        _add(item, "location_alerts")

    for item in ((raw.get("address_alerts") or {}).get("alerts") or []):
        _add(item, "address_alerts")

    return merged


class DisasterAggregator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cycle_lock = threading.Lock()

    def run_cycle(self) -> Dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            return {"status": "BUSY", "message": "Previous sync cycle still running"}

        try:
            stagger = max(0.0, self.settings.source_stagger_seconds)

            summary = {
                "collector_snapshot": self._sync_collector_snapshot(),
            }
            if stagger:
                time.sleep(stagger)

            summary["ndma_sachet"] = self._sync_ndma()
            if stagger:
                time.sleep(stagger)

            summary["data_gov_in"] = self._sync_ogd()
            if stagger:
                time.sleep(stagger)

            summary["mosdac"] = self._sync_mosdac()
            LOGGER.info("Sync summary: %s", summary)
            return summary
        finally:
            self._cycle_lock.release()

    def _sync_collector_snapshot(self) -> Dict[str, Any]:
        source = "collector_snapshot"
        if not self.settings.enable_collector_snapshot:
            db.record_source_run(
                self.settings.database_url,
                source,
                status="SKIPPED",
                error="ENABLE_COLLECTOR_SNAPSHOT is false",
            )
            return {"status": "SKIPPED", "records": 0}

        snapshot_path = self.settings.collector_alert_json
        if not snapshot_path:
            db.record_source_run(
                self.settings.database_url,
                source,
                status="SKIPPED",
                error="COLLECTOR_ALERT_JSON not configured",
            )
            return {"status": "SKIPPED", "records": 0}

        if not os.path.exists(snapshot_path):
            db.record_source_run(
                self.settings.database_url,
                source,
                status="ERROR",
                error=f"Snapshot file not found: {snapshot_path}",
            )
            return {"status": "ERROR", "records": 0, "error": f"File not found: {snapshot_path}"}

        try:
            with open(snapshot_path, "r", encoding="utf-8") as file:
                payload = json.load(file)

            records = _collector_records_from_snapshot(payload if isinstance(payload, dict) else {})
            alerts = _normalize_records(records, source)
            stored = db.upsert_alerts(self.settings.database_url, alerts)
            db.record_source_run(self.settings.database_url, source, status="SUCCESS", records_fetched=stored)
            return {"status": "SUCCESS", "records": stored}
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Collector snapshot sync failed")
            db.record_source_run(self.settings.database_url, source, status="ERROR", error=str(exc))
            return {"status": "ERROR", "records": 0, "error": str(exc)}

    def _sync_ndma(self) -> Dict[str, Any]:
        source = "ndma_sachet"
        try:
            xml_bytes = fetch_ndma_cap_feed(
                self.settings.ndma_cap_url,
                self.settings.http_timeout_seconds,
                retries=self.settings.request_retries,
                backoff_seconds=self.settings.request_backoff_seconds,
            )
            alerts = parse_cap_alerts(xml_bytes, source_name=source)
            stored = db.upsert_alerts(self.settings.database_url, alerts)
            db.record_source_run(self.settings.database_url, source, status="SUCCESS", records_fetched=stored)
            return {"status": "SUCCESS", "records": stored}
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("NDMA sync failed")
            db.record_source_run(self.settings.database_url, source, status="ERROR", error=str(exc))
            return {"status": "ERROR", "records": 0, "error": str(exc)}

    def _sync_ogd(self) -> Dict[str, Any]:
        source = "data_gov_in"
        if not self.settings.ogd_dataset_url:
            db.record_source_run(
                self.settings.database_url,
                source,
                status="SKIPPED",
                error="OGD_DATASET_URL not configured",
            )
            return {"status": "SKIPPED", "records": 0}

        try:
            records = fetch_ogd_records(
                self.settings.ogd_dataset_url,
                timeout_seconds=self.settings.http_timeout_seconds,
                api_key=self.settings.ogd_api_key,
                retries=self.settings.request_retries,
                backoff_seconds=self.settings.request_backoff_seconds,
            )
            alerts = _normalize_records(records, source)
            stored = db.upsert_alerts(self.settings.database_url, alerts)
            db.record_source_run(self.settings.database_url, source, status="SUCCESS", records_fetched=stored)
            return {"status": "SUCCESS", "records": stored}
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("OGD sync failed")
            db.record_source_run(self.settings.database_url, source, status="ERROR", error=str(exc))
            return {"status": "ERROR", "records": 0, "error": str(exc)}

    def _sync_mosdac(self) -> Dict[str, Any]:
        source = "mosdac"
        if not self.settings.mosdac_endpoint_url:
            db.record_source_run(
                self.settings.database_url,
                source,
                status="SKIPPED",
                error="MOSDAC_ENDPOINT_URL not configured",
            )
            return {"status": "SKIPPED", "records": 0}

        try:
            records = fetch_mosdac_records(
                self.settings.mosdac_endpoint_url,
                timeout_seconds=self.settings.http_timeout_seconds,
                api_token=self.settings.mosdac_api_token,
                retries=self.settings.request_retries,
                backoff_seconds=self.settings.request_backoff_seconds,
            )
            alerts = _normalize_records(records, source)
            stored = db.upsert_alerts(self.settings.database_url, alerts)
            db.record_source_run(self.settings.database_url, source, status="SUCCESS", records_fetched=stored)
            return {"status": "SUCCESS", "records": stored}
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("MOSDAC sync failed")
            db.record_source_run(self.settings.database_url, source, status="ERROR", error=str(exc))
            return {"status": "ERROR", "records": 0, "error": str(exc)}
