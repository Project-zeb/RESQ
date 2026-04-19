import hashlib
import xml.etree.ElementTree as ET
from typing import List, Optional

from disaster_api.models.alert_model import Alert


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", maxsplit=1)[-1]
    return tag


def _child_text(parent: ET.Element, child_name: str) -> Optional[str]:
    for child in list(parent):
        if _local_name(child.tag) == child_name and child.text:
            text = child.text.strip()
            if text:
                return text
    return None


def _descendant_text(parent: ET.Element, element_name: str) -> Optional[str]:
    for node in parent.iter():
        if _local_name(node.tag) == element_name and node.text:
            text = node.text.strip()
            if text:
                return text
    return None


def _children(parent: ET.Element, element_name: str) -> List[ET.Element]:
    return [node for node in list(parent) if _local_name(node.tag) == element_name]


def _find_cap_alert_nodes(root: ET.Element) -> List[ET.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == "alert"]


def parse_cap_alerts(xml_bytes: bytes, source_name: str = "ndma_sachet") -> List[Alert]:
    root = ET.fromstring(xml_bytes)
    alert_nodes = _find_cap_alert_nodes(root)
    parsed: List[Alert] = []

    for alert_node in alert_nodes:
        info_nodes = _children(alert_node, "info")
        info = info_nodes[0] if info_nodes else alert_node

        identifier = _descendant_text(alert_node, "identifier")
        if not identifier:
            identifier = hashlib.sha256(ET.tostring(alert_node)).hexdigest()

        areas = []
        for area_node in _children(info, "area"):
            area_desc = _child_text(area_node, "areaDesc")
            if area_desc:
                areas.append(area_desc)

        category = _descendant_text(info, "category")
        event_type = _descendant_text(info, "event") or category

        parsed.append(
            Alert(
                source=source_name,
                external_id=identifier,
                event_type=event_type,
                severity=_descendant_text(info, "severity"),
                urgency=_descendant_text(info, "urgency"),
                certainty=_descendant_text(info, "certainty"),
                area=", ".join(areas) if areas else _descendant_text(info, "areaDesc"),
                status=_descendant_text(alert_node, "status"),
                issued_at=_descendant_text(alert_node, "sent"),
                effective_at=_descendant_text(info, "effective"),
                expires_at=_descendant_text(info, "expires"),
                headline=_descendant_text(info, "headline"),
                description=_descendant_text(info, "description"),
                instruction=_descendant_text(info, "instruction"),
                payload={
                    "identifier": identifier,
                    "sender": _descendant_text(alert_node, "sender"),
                    "category": category,
                    "language": _descendant_text(info, "language"),
                    "scope": _descendant_text(alert_node, "scope"),
                },
            )
        )

    return parsed
