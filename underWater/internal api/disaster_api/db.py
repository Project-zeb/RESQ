import json
import hashlib
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    create_engine,
    desc,
    event,
    func,
    or_,
    select,
)
from sqlalchemy.engine import Engine

from disaster_api.models.alert_model import Alert


_ENGINE_LOCK = threading.Lock()
_ENGINE_CACHE: Dict[str, Engine] = {}
_METADATA = MetaData()
metadata = _METADATA


alerts_table = Table(
    "alerts",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source", String(120), nullable=False),
    Column("external_id", String(255), nullable=False),
    Column("event_type", String(255)),
    Column("severity", String(128)),
    Column("urgency", String(128)),
    Column("certainty", String(128)),
    Column("area", Text),
    Column("status", String(64)),
    Column("issued_at", String(64)),
    Column("effective_at", String(64)),
    Column("expires_at", String(64)),
    Column("headline", Text),
    Column("description", Text),
    Column("instruction", Text),
    Column("payload_json", Text),
    Column("fetched_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("source", "external_id", name="uq_alert_source_external_id"),
    Index("idx_alerts_issued_at", "issued_at"),
    Index("idx_alerts_source", "source"),
    sqlite_autoincrement=True,
)

source_runs_table = Table(
    "source_runs",
    _METADATA,
    Column("source", String(120), primary_key=True),
    Column("last_status", String(32), nullable=False),
    Column("last_attempt_at", String(64), nullable=False),
    Column("last_success_at", String(64)),
    Column("last_error", Text),
    Column("records_fetched", Integer, nullable=False, default=0),
    Column("updated_at", String(64), nullable=False),
)

api_keys_table = Table(
    "api_keys",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("key_hash", String(128), nullable=False),
    Column("role", String(32), nullable=False),
    Column("label", String(255)),
    Column("created_at", String(64), nullable=False),
    Column("expires_at", String(64)),
    Column("revoked_at", String(64)),
    Column("last_used_at", String(64)),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    Index("idx_api_keys_role", "role"),
    sqlite_autoincrement=True,
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _to_utc_iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, seconds))).replace(microsecond=0).isoformat()


def _get_engine(database_url: str) -> Engine:
    with _ENGINE_LOCK:
        engine = _ENGINE_CACHE.get(database_url)
        if engine:
            return engine

        connect_args: Dict[str, Any] = {}
        if database_url.startswith("sqlite:///"):
            connect_args = {"check_same_thread": False, "timeout": 30}

        engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        if engine.dialect.name == "sqlite":
            @event.listens_for(engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.close()

        _ENGINE_CACHE[database_url] = engine
        return engine


def init_db(database_url: str) -> None:
    engine = _get_engine(database_url)
    _METADATA.create_all(engine)


def _normalize_alert(alert: Union[Alert, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(alert, Alert):
        return alert.to_storage_dict()
    return alert


def _serialize_payload(payload: Any) -> str:
    if payload is None:
        return "{}"
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _on_conflict_upsert_alerts(database_url: str, rows: List[Dict[str, Any]]) -> None:
    engine = _get_engine(database_url)
    update_columns = [
        "event_type",
        "severity",
        "urgency",
        "certainty",
        "area",
        "status",
        "issued_at",
        "effective_at",
        "expires_at",
        "headline",
        "description",
        "instruction",
        "payload_json",
        "fetched_at",
        "updated_at",
    ]

    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        base_stmt = pg_insert(alerts_table).values(rows)
        upsert_stmt = base_stmt.on_conflict_do_update(
            index_elements=["source", "external_id"],
            set_={column: getattr(base_stmt.excluded, column) for column in update_columns},
        )
        with engine.begin() as conn:
            conn.execute(upsert_stmt)
        return

    if engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        base_stmt = sqlite_insert(alerts_table).values(rows)
        upsert_stmt = base_stmt.on_conflict_do_update(
            index_elements=["source", "external_id"],
            set_={column: getattr(base_stmt.excluded, column) for column in update_columns},
        )
        with engine.begin() as conn:
            conn.execute(upsert_stmt)
        return

    with engine.begin() as conn:
        for row in rows:
            exists = conn.execute(
                select(alerts_table.c.id).where(
                    and_(
                        alerts_table.c.source == row["source"],
                        alerts_table.c.external_id == row["external_id"],
                    )
                )
            ).first()
            if exists:
                conn.execute(
                    alerts_table.update()
                    .where(
                        and_(
                            alerts_table.c.source == row["source"],
                            alerts_table.c.external_id == row["external_id"],
                        )
                    )
                    .values(**{k: row[k] for k in update_columns})
                )
            else:
                conn.execute(alerts_table.insert().values(**row))


def upsert_alerts(
    database_url: str,
    alerts: Iterable[Union[Alert, Dict[str, Any]]],
) -> int:
    now = utcnow_iso()
    normalized_rows: List[Dict[str, Any]] = []

    for incoming in alerts:
        item = _normalize_alert(incoming)
        normalized_rows.append(
            {
                "source": item.get("source"),
                "external_id": item.get("external_id"),
                "event_type": item.get("event_type"),
                "severity": item.get("severity"),
                "urgency": item.get("urgency"),
                "certainty": item.get("certainty"),
                "area": item.get("area"),
                "status": item.get("status"),
                "issued_at": item.get("issued_at"),
                "effective_at": item.get("effective_at"),
                "expires_at": item.get("expires_at"),
                "headline": item.get("headline"),
                "description": item.get("description"),
                "instruction": item.get("instruction"),
                "payload_json": _serialize_payload(item.get("payload")),
                "fetched_at": now,
                "updated_at": now,
            }
        )

    if not normalized_rows:
        return 0

    _on_conflict_upsert_alerts(database_url, normalized_rows)
    return len(normalized_rows)


def record_source_run(
    database_url: str,
    source: str,
    status: str,
    records_fetched: int = 0,
    error: Optional[str] = None,
) -> None:
    now = utcnow_iso()
    last_success_at = now if status == "SUCCESS" else None
    row = {
        "source": source,
        "last_status": status,
        "last_attempt_at": now,
        "last_success_at": last_success_at,
        "last_error": error,
        "records_fetched": records_fetched,
        "updated_at": now,
    }

    engine = _get_engine(database_url)
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        base_stmt = pg_insert(source_runs_table).values(**row)
        upsert_stmt = base_stmt.on_conflict_do_update(
            index_elements=["source"],
            set_={
                "last_status": base_stmt.excluded.last_status,
                "last_attempt_at": base_stmt.excluded.last_attempt_at,
                "last_success_at": func.coalesce(
                    base_stmt.excluded.last_success_at, source_runs_table.c.last_success_at
                ),
                "last_error": base_stmt.excluded.last_error,
                "records_fetched": base_stmt.excluded.records_fetched,
                "updated_at": base_stmt.excluded.updated_at,
            },
        )
        with engine.begin() as conn:
            conn.execute(upsert_stmt)
        return

    if engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        base_stmt = sqlite_insert(source_runs_table).values(**row)
        upsert_stmt = base_stmt.on_conflict_do_update(
            index_elements=["source"],
            set_={
                "last_status": base_stmt.excluded.last_status,
                "last_attempt_at": base_stmt.excluded.last_attempt_at,
                "last_success_at": func.coalesce(
                    base_stmt.excluded.last_success_at, source_runs_table.c.last_success_at
                ),
                "last_error": base_stmt.excluded.last_error,
                "records_fetched": base_stmt.excluded.records_fetched,
                "updated_at": base_stmt.excluded.updated_at,
            },
        )
        with engine.begin() as conn:
            conn.execute(upsert_stmt)
        return

    with engine.begin() as conn:
        exists = conn.execute(
            select(source_runs_table.c.source).where(source_runs_table.c.source == source)
        ).first()
        if exists:
            values = dict(row)
            if values["last_success_at"] is None:
                values.pop("last_success_at")
            conn.execute(
                source_runs_table.update().where(source_runs_table.c.source == source).values(**values)
            )
        else:
            conn.execute(source_runs_table.insert().values(**row))


def _row_to_alert(row: Dict[str, Any]) -> Dict[str, Any]:
    payload_json = row.get("payload_json") or "{}"
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        payload = {"raw_payload": payload_json}

    return {
        "id": row.get("id"),
        "source": row.get("source"),
        "external_id": row.get("external_id"),
        "event_type": row.get("event_type"),
        "severity": row.get("severity"),
        "urgency": row.get("urgency"),
        "certainty": row.get("certainty"),
        "area": row.get("area"),
        "status": row.get("status"),
        "issued_at": row.get("issued_at"),
        "effective_at": row.get("effective_at"),
        "expires_at": row.get("expires_at"),
        "headline": row.get("headline"),
        "description": row.get("description"),
        "instruction": row.get("instruction"),
        "payload": payload,
        "fetched_at": row.get("fetched_at"),
        "updated_at": row.get("updated_at"),
    }


def list_alerts(
    database_url: str,
    limit: int = 200,
    source: Optional[str] = None,
    severity: Optional[str] = None,
    area: Optional[str] = None,
    since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, 5000))
    recency_column = func.coalesce(
        alerts_table.c.issued_at,
        alerts_table.c.effective_at,
        alerts_table.c.updated_at,
        alerts_table.c.fetched_at,
    )
    query = select(alerts_table).order_by(
        desc(recency_column),
        desc(alerts_table.c.updated_at),
        desc(alerts_table.c.id),
    )

    if source:
        query = query.where(alerts_table.c.source == source)
    if severity:
        query = query.where(alerts_table.c.severity == severity)
    if area:
        lowered = f"%{area.lower()}%"
        query = query.where(func.lower(alerts_table.c.area).like(lowered))
    if since:
        query = query.where(recency_column >= since)

    query = query.limit(safe_limit)
    engine = _get_engine(database_url)
    with engine.begin() as conn:
        rows = conn.execute(query).mappings().all()
    return [_row_to_alert(dict(row)) for row in rows]


def get_alert_by_id(database_url: str, alert_id: int) -> Optional[Dict[str, Any]]:
    engine = _get_engine(database_url)
    with engine.begin() as conn:
        row = (
            conn.execute(select(alerts_table).where(alerts_table.c.id == alert_id)).mappings().first()
        )
    if not row:
        return None
    return _row_to_alert(dict(row))


def get_source_runs(database_url: str) -> List[Dict[str, Any]]:
    query = select(source_runs_table).order_by(source_runs_table.c.source.asc())
    engine = _get_engine(database_url)
    with engine.begin() as conn:
        rows = conn.execute(query).mappings().all()
    return [dict(row) for row in rows]


def _active_key_condition(now_iso: str):
    return and_(
        api_keys_table.c.revoked_at.is_(None),
        or_(api_keys_table.c.expires_at.is_(None), api_keys_table.c.expires_at > now_iso),
    )


def _insert_bootstrap_key(database_url: str, raw_key: str, role: str, label: str) -> None:
    if not raw_key:
        return

    key_hash = _hash_key(raw_key)
    now = utcnow_iso()
    engine = _get_engine(database_url)
    with engine.begin() as conn:
        existing = conn.execute(
            select(api_keys_table.c.id, api_keys_table.c.role).where(api_keys_table.c.key_hash == key_hash)
        ).first()
        if existing:
            existing_id, existing_role = int(existing[0]), str(existing[1])
            if role == "admin" and existing_role != "admin":
                conn.execute(
                    api_keys_table.update()
                    .where(api_keys_table.c.id == existing_id)
                    .values(role="admin", label=label, updated_at=now)
                )
            return
        conn.execute(
            api_keys_table.insert().values(
                key_hash=key_hash,
                role=role,
                label=label,
                created_at=now,
                updated_at=now,
            )
        )


def init_key_store(
    database_url: str,
    bootstrap_api_key: str,
    bootstrap_admin_key: str,
) -> None:
    _insert_bootstrap_key(database_url, bootstrap_api_key, role="api", label="bootstrap-api")
    _insert_bootstrap_key(database_url, bootstrap_admin_key, role="admin", label="bootstrap-admin")


def verify_api_key(
    database_url: str,
    raw_key: str,
    allowed_roles: Sequence[str],
) -> Optional[Dict[str, Any]]:
    if not raw_key:
        return None
    key_hash = _hash_key(raw_key)
    now = utcnow_iso()
    roles = list(allowed_roles) or ["api"]

    query = (
        select(api_keys_table)
        .where(api_keys_table.c.key_hash == key_hash)
        .where(api_keys_table.c.role.in_(roles))
        .where(_active_key_condition(now))
        .limit(1)
    )

    engine = _get_engine(database_url)
    with engine.begin() as conn:
        row = conn.execute(query).mappings().first()
        if not row:
            return None
        conn.execute(
            api_keys_table.update()
            .where(api_keys_table.c.id == row["id"])
            .values(last_used_at=now, updated_at=now)
        )

    return {
        "id": row["id"],
        "role": row["role"],
        "label": row["label"],
        "created_at": row["created_at"],
    }


def rotate_api_key(
    database_url: str,
    grace_seconds: int,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    now = utcnow_iso()
    safe_grace = max(0, int(grace_seconds))
    grace_expires_at = _to_utc_iso_after(safe_grace) if safe_grace > 0 else None
    new_key_value = secrets.token_urlsafe(48)
    new_key_hash = _hash_key(new_key_value)
    new_label = (label or "").strip() or f"rotated-{now}"

    engine = _get_engine(database_url)
    with engine.begin() as conn:
        old_rows = conn.execute(
            select(api_keys_table.c.id).where(api_keys_table.c.role == "api").where(_active_key_condition(now))
        ).all()
        old_ids = [row[0] for row in old_rows]

        insert_result = conn.execute(
            api_keys_table.insert().values(
                key_hash=new_key_hash,
                role="api",
                label=new_label,
                created_at=now,
                updated_at=now,
            )
        )
        new_key_id = int(insert_result.inserted_primary_key[0]) if insert_result.inserted_primary_key else None

        if old_ids:
            if safe_grace > 0:
                conn.execute(
                    api_keys_table.update()
                    .where(api_keys_table.c.id.in_(old_ids))
                    .values(expires_at=grace_expires_at, updated_at=now)
                )
            else:
                conn.execute(
                    api_keys_table.update()
                    .where(api_keys_table.c.id.in_(old_ids))
                    .values(revoked_at=now, updated_at=now)
                )

    return {
        "new_api_key": new_key_value,
        "new_key_id": new_key_id,
        "grace_seconds": safe_grace,
        "grace_expires_at": grace_expires_at,
        "rotated_keys_count": len(old_ids),
    }


def list_api_keys(database_url: str) -> List[Dict[str, Any]]:
    query = select(
        api_keys_table.c.id,
        api_keys_table.c.role,
        api_keys_table.c.label,
        api_keys_table.c.created_at,
        api_keys_table.c.expires_at,
        api_keys_table.c.revoked_at,
        api_keys_table.c.last_used_at,
        api_keys_table.c.updated_at,
    ).order_by(api_keys_table.c.id.desc())

    engine = _get_engine(database_url)
    with engine.begin() as conn:
        rows = conn.execute(query).mappings().all()
    return [dict(row) for row in rows]
