from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

import jwt
from jwt import InvalidTokenError

from disaster_api import db
from disaster_api.config import Settings


def _extract_bearer_token(request: Any) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class AuthService:
    def __init__(self, settings: Settings):
        self.settings = settings
        bootstrap_admin = settings.admin_api_key or settings.internal_api_key
        db.init_key_store(settings.database_url, settings.internal_api_key, bootstrap_admin)

    def authenticate_request(self, request: Any, require_admin: bool = False) -> Optional[Dict[str, Any]]:
        bearer_value = _extract_bearer_token(request)

        if bearer_value:
            jwt_claims = self._verify_jwt(bearer_value)
            if jwt_claims:
                role = jwt_claims.get("role", "api")
                if require_admin and role != "admin":
                    return None
                return {
                    "auth_type": "jwt",
                    "role": role,
                    "subject": jwt_claims.get("sub", "jwt-client"),
                }

        candidate_keys: Set[str] = set()
        key_from_header = request.headers.get(self.settings.api_key_header, "").strip()
        if key_from_header:
            candidate_keys.add(key_from_header)

        admin_key_from_header = request.headers.get(self.settings.admin_api_key_header, "").strip()
        if admin_key_from_header:
            candidate_keys.add(admin_key_from_header)

        if bearer_value:
            candidate_keys.add(bearer_value)

        if not candidate_keys:
            return None

        allowed_roles = ["admin"] if require_admin else ["api", "admin"]
        for candidate in candidate_keys:
            key_record = db.verify_api_key(
                self.settings.database_url,
                raw_key=candidate,
                allowed_roles=allowed_roles,
            )
            if not key_record:
                continue
            return {
                "auth_type": "api_key",
                "role": key_record["role"],
                "subject": f"key:{key_record['id']}",
                "key_id": key_record["id"],
            }

        return None

    def issue_jwt(self, principal: Dict[str, Any], requested_minutes: Any = None) -> Dict[str, Any]:
        ttl_minutes = _as_int(requested_minutes, self.settings.jwt_expires_minutes)
        ttl_minutes = max(1, min(ttl_minutes, self.settings.jwt_max_expires_minutes))
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl_minutes)

        claims = {
            "sub": principal.get("subject", "internal-client"),
            "role": principal.get("role", "api"),
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
        }

        token = jwt.encode(claims, self._jwt_secret(), algorithm=self.settings.jwt_algorithm)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in_seconds": ttl_minutes * 60,
            "expires_at": expires_at.replace(microsecond=0).isoformat(),
            "role": claims["role"],
        }

    def rotate_api_key(self, grace_seconds: Any = None, label: Optional[str] = None) -> Dict[str, Any]:
        safe_grace = _as_int(grace_seconds, 300)
        safe_grace = max(0, min(safe_grace, 86400))
        return db.rotate_api_key(self.settings.database_url, grace_seconds=safe_grace, label=label)

    def list_api_keys(self) -> Dict[str, Any]:
        items = db.list_api_keys(self.settings.database_url)
        return {"count": len(items), "items": items}

    def _jwt_secret(self) -> str:
        return self.settings.jwt_secret or self.settings.internal_api_key or self.settings.admin_api_key

    def _verify_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        secret = self._jwt_secret()
        if not secret:
            return None
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self.settings.jwt_algorithm],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
            )
        except InvalidTokenError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload
