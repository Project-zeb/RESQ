from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Alert:
    source: str
    external_id: str
    event_type: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    certainty: Optional[str] = None
    area: Optional[str] = None
    status: Optional[str] = None
    issued_at: Optional[str] = None
    effective_at: Optional[str] = None
    expires_at: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    instruction: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_storage_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "external_id": self.external_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "urgency": self.urgency,
            "certainty": self.certainty,
            "area": self.area,
            "status": self.status,
            "issued_at": self.issued_at,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
            "headline": self.headline,
            "description": self.description,
            "instruction": self.instruction,
            "payload": self.payload,
        }
