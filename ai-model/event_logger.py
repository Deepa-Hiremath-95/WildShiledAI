"""
WildShield AI - Phase 2: Event Logging Module
==============================================
Module 7:
Structured event recording for all evaluations, actions, and siren operations.

Mandatory Fields per Phase 2 Specifications:
- Event ID
- Timestamp
- Detection class
- Confidence
- Camera ID
- Village ID
- Zone ID
- Risk level
- Action taken
- Siren configuration selected
- Siren playback status
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class EventRecord:
    """Full structured event record for WildShield AI Phase 2."""
    event_id: str
    timestamp: float
    detection_class: str
    confidence: float
    camera_id: str
    village_id: Optional[str]
    zone_id: Optional[str]
    risk_level: str
    action_taken: str
    siren_config_selected: Optional[str]
    siren_playback_status: str
    village_name: Optional[str] = None
    zone_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to JSON-serializable dictionary."""
        d = asdict(self)
        d["timestamp_iso"] = datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()
        return d

    def format_terminal(self) -> str:
        """Formatted multi-line summary matching Phase 2 terminal specifications."""
        conf_pct = int(round(self.confidence * 100))
        lines = [
            f"[DETECTION] {self.detection_class} | Confidence: {conf_pct}%",
            f"[LOCATION] Village: {self.village_name or self.village_id or 'Unknown'} | Camera: {self.camera_id}",
            f"[ZONE] {self.zone_name or self.zone_id or 'Unknown'}",
            f"[RISK] {self.risk_level}",
            f"[ACTION] {self.action_taken}",
        ]
        if self.siren_playback_status == "PLAYED":
            lines.append(f"[SIREN] {self.village_name or 'Village'} sound selected")
        elif self.siren_playback_status == "NOT_ACTIVATED_HUMAN":
            lines.append("[SIREN] Not activated")
        elif self.siren_playback_status == "SUPPRESSED_COOLDOWN":
            lines.append("[SIREN] Cooldown active - suppressed")
        else:
            lines.append(f"[SIREN] {self.siren_playback_status}")

        return "\n".join(lines)


class EventLogger:
    """Thread-safe event logger supporting in-memory and persistent JSONL history."""

    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file
        self.events: List[EventRecord] = []
        self._lock = threading.Lock()

    def clear(self):
        """Clears in-memory log entries."""
        with self._lock:
            self.events.clear()

    def log(
        self,
        detection_class: str,
        confidence: float,
        camera_id: str,
        village_id: Optional[str],
        zone_id: Optional[str],
        risk_level: str,
        action_taken: str,
        siren_config_selected: Optional[str],
        siren_playback_status: str,
        village_name: Optional[str] = None,
        zone_name: Optional[str] = None,
        timestamp: Optional[float] = None,
        event_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> EventRecord:
        """Records a new event and returns the created EventRecord."""
        record = EventRecord(
            event_id=event_id or f"EVT-{uuid.uuid4().hex[:8].upper()}",
            timestamp=timestamp if timestamp is not None else time.time(),
            detection_class=detection_class,
            confidence=confidence,
            camera_id=camera_id,
            village_id=village_id,
            zone_id=zone_id,
            risk_level=risk_level,
            action_taken=action_taken,
            siren_config_selected=siren_config_selected,
            siren_playback_status=siren_playback_status,
            village_name=village_name,
            zone_name=zone_name,
            details=details or {},
        )

        with self._lock:
            self.events.append(record)

            if self.log_file:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(self.log_file)), exist_ok=True)
                    with open(self.log_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record.to_dict()) + "\n")
                except Exception:
                    pass

        return record

    def get_latest(self) -> Optional[EventRecord]:
        """Returns most recent event or None."""
        with self._lock:
            return self.events[-1] if self.events else None

    def get_all(self) -> List[EventRecord]:
        """Returns snapshot copy of all recorded events."""
        with self._lock:
            return list(self.events)

