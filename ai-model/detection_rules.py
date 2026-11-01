"""
WildShield AI - Phase 2: Detection Rule Engine & Integrated Pipeline
====================================================================
Modular rule engine responsible for evaluating raw object detections from
Roboflow/YOLO against:
- Configurable Village Management (Module 1)
- Camera & Zone Association (Module 2)
- Detection Rules & Normalized Classes (Module 3)
- Multi-Zone Management (Module 4)
- Risk Assessment Engine (Module 5)
- Village-Specific Laptop Siren Selection (Module 6)
- Comprehensive Event Logging (Module 7)
- Terminal Output Specifications (Module 9)

Supported Wildlife Classes:
- Elephant, Deer, Leopard, Wild_boar -> Animal Alert Required
- Human -> Human Notification Recorded (NEVER activates siren)
- Peacock -> Ignored (Excluded class)
- Unknown / Unsupported -> Ignored
- Low Confidence (< 0.60 default) -> Ignored

Camera-Driven Identity:
- Camera identity assigns Village ID and Zone ID without guessing
  coordinates from animal images.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from event_logger import EventLogger, EventRecord
from risk_engine import RiskAssessmentEngine, RiskAssessmentResult, RiskLevel
from siren_service import SirenPlaybackResult, SirenService, SirenStatus
from village_manager import (
    CameraConfig,
    EmergencyContact,
    SirenConfig,
    VillageConfig,
    VillageManager,
    ZoneConfig,
    ZoneType,
)


# ---------------------------------------------------------------------------
# Enums and Constants
# ---------------------------------------------------------------------------
class RuleAction(str, Enum):
    ANIMAL_ALERT_REQUIRED = "ANIMAL_ALERT_REQUIRED"
    HUMAN_NOTIFICATION_REQUIRED = "HUMAN_NOTIFICATION_REQUIRED"
    IGNORED = "IGNORED"


# Re-export Zone as alias for ZoneConfig for backward compatibility
Zone = ZoneConfig

# Supported Classes
ANIMAL_CLASSES = {"elephant", "deer", "leopard", "wild_boar", "wild boar", "wildboar"}
HUMAN_CLASSES = {"human", "person"}
EXCLUDED_CLASSES = {"peacock"}


def normalize_class_name(raw_name: str) -> str:
    """Normalize raw class names to canonical forms."""
    if not raw_name:
        return "Unknown"
    cleaned = raw_name.strip().lower()
    if cleaned in {"wild_boar", "wild boar", "wildboar"}:
        return "Wild_boar"
    if cleaned in HUMAN_CLASSES:
        return "Human"
    if cleaned in EXCLUDED_CLASSES:
        return "Peacock"
    if cleaned == "elephant":
        return "Elephant"
    if cleaned == "deer":
        return "Deer"
    if cleaned == "leopard":
        return "Leopard"
    return raw_name.strip().capitalize()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    """Represents a single object detection from an inference model or webcam."""
    class_name: str
    confidence: float
    box: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2)
    track_id: Optional[Union[int, str]] = None
    timestamp: float = field(default_factory=time.time)
    camera_id: str = "CAM-001"


@dataclass
class RuleDecision:
    """Represents the complete outcome of rule-engine evaluation for a detection."""
    is_event: bool
    action: RuleAction
    class_name: str
    confidence: float
    camera_id: str = "CAM-001"
    village_id: Optional[str] = None
    village_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None
    action_text: Optional[str] = None
    siren_pattern: Optional[str] = None
    siren_status: Optional[str] = None
    reason: Optional[str] = None
    event_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def format_terminal(self, legacy: bool = False) -> str:
        """
        Formats output strictly following Phase 2 specifications (Module 9):
        Animal:
          [DETECTION] Elephant | Confidence: 94%
          [LOCATION] Village: Village A | Camera: CAM-001
          [ZONE] Forest Boundary
          [RISK] HIGH
          [ACTION] Animal alert required
          [SIREN] Village A sound selected
        Human:
          [DETECTION] Human | Confidence: 91%
          [ACTION] Human detection recorded
          [SIREN] Not activated
        Ignored:
          [IGNORED] Peacock | Reason: Excluded class
        """
        conf_pct = int(round(self.confidence * 100))

        if legacy:
            return self.format_legacy()

        if not self.is_event:
            return f"[IGNORED] {self.class_name} | Reason: {self.reason}"

        if self.class_name == "Human":
            return (
                f"[DETECTION] Human | Confidence: {conf_pct}%\n"
                f"[ACTION] Human detection recorded\n"
                f"[SIREN] Not activated"
            )

        # Animal detection output
        vil_str = self.village_name or self.village_id or "Village A"
        cam_str = self.camera_id or "CAM-001"
        zone_str = self.zone_name or self.zone_id or "Forest Boundary"
        risk_str = self.risk_level or "HIGH"
        act_str = self.action_text or "Animal alert required"

        lines = [
            f"[DETECTION] {self.class_name} | Confidence: {conf_pct}%",
            f"[LOCATION] Village: {vil_str} | Camera: {cam_str}",
            f"[ZONE] {zone_str}",
            f"[RISK] {risk_str}",
            f"[ACTION] {act_str}",
        ]

        if self.siren_status == "PLAYED":
            lines.append(f"[SIREN] {vil_str} sound selected")
        elif self.siren_status == "SUPPRESSED_COOLDOWN":
            lines.append(f"[SIREN] {vil_str} sound cooldown active")
        else:
            lines.append(f"[SIREN] {self.siren_status or 'Not activated'}")

        return "\n".join(lines)

    def format_legacy(self) -> str:
        """Legacy single-line format for backward compatibility with earlier unit tests."""
        conf_pct = int(round(self.confidence * 100))
        if self.is_event:
            return (
                f"[EVENT] {self.class_name} | Confidence: {conf_pct}% | "
                f"Zone: {self.zone_name} | Action: {self.action.value}"
            )
        else:
            return f"[IGNORED] {self.class_name} | Reason: {self.reason}"

    def __str__(self) -> str:
        return self.format_terminal()


# ---------------------------------------------------------------------------
# Bounding Box Math Helper
# ---------------------------------------------------------------------------
def compute_iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    """Compute Intersection over Union (IoU) between two bounding boxes."""
    xA = max(box_a[0], box_b[0])
    yA = max(box_a[1], box_b[1])
    xB = min(box_a[2], box_b[2])
    yB = min(box_a[3], box_b[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    denom = float(area_a + area_b - inter_area)

    return inter_area / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Detection Rule Engine
# ---------------------------------------------------------------------------
class DetectionRuleEngine:
    """
    Evaluates detections against configurable business rules, villages, zones,
    deduplication records, cooldown timers, risk assessments, and laptop sirens.
    """

    def __init__(
        self,
        default_confidence_threshold: float = 0.60,
        default_cooldown_seconds: float = 90.0,
        duplicate_window_seconds: float = 10.0,
        default_human_cooldown_seconds: float = 0.0,
        village_manager: Optional[VillageManager] = None,
        risk_engine: Optional[RiskAssessmentEngine] = None,
        siren_service: Optional[SirenService] = None,
        event_logger: Optional[EventLogger] = None,
        dry_run_audio: bool = False,
    ):
        self.default_confidence_threshold = default_confidence_threshold
        self.default_cooldown_seconds = default_cooldown_seconds
        self.duplicate_window_seconds = duplicate_window_seconds
        self.default_human_cooldown_seconds = default_human_cooldown_seconds

        # Modular Subsystems
        self.village_manager = village_manager or VillageManager()
        self.risk_engine = risk_engine or RiskAssessmentEngine()
        self.siren_service = siren_service or SirenService(
            default_cooldown_seconds=default_cooldown_seconds,
            dry_run=dry_run_audio,
        )
        self.event_logger = event_logger or EventLogger()

        # Backward compatibility default zones
        self.animal_zone = self.village_manager.zones.get("ZONE-A-FB") or ZoneConfig(
            id="zone-animal-default",
            name="Animal Zone",
            zone_type=ZoneType.FOREST_BOUNDARY_ZONE,
            confidence_threshold=default_confidence_threshold,
            cooldown_seconds=default_cooldown_seconds,
        )
        self.restricted_zone = self.village_manager.zones.get("ZONE-A-RES") or ZoneConfig(
            id="zone-restricted-default",
            name="Restricted Zone",
            zone_type=ZoneType.RESTRICTED_ZONE,
            confidence_threshold=default_confidence_threshold,
            cooldown_seconds=default_cooldown_seconds,
        )

        # Dictionary of zones for compatibility
        self.zones = self.village_manager.zones

        # State tracking:
        # Zone last alert timestamps: zone_id -> timestamp (float)
        self._zone_last_alert: Dict[str, float] = {}
        self._zone_last_animal_alert: Dict[str, float] = {}
        self._zone_last_human_alert: Dict[str, float] = {}

        # Track ID last alert timestamps: track_id -> timestamp (float)
        self._track_last_alert: Dict[Union[int, str], float] = {}

        # Spatial/Temporal recent alerts for duplicate suppression when track_id is absent:
        # List of dicts: [{'class_name': str, 'zone_id': str, 'box': box, 'timestamp': float}]
        self._recent_events: List[Dict[str, Any]] = []

    def reset_state(self):
        """Clears all cooldowns, track histories, and duplicate logs."""
        self._zone_last_alert.clear()
        self._zone_last_animal_alert.clear()
        self._zone_last_human_alert.clear()
        self._track_last_alert.clear()
        self._recent_events.clear()
        self.risk_engine.reset_state()
        self.siren_service.reset_state()
        self.event_logger.clear()

    def set_zone_cooldown(
        self,
        zone_id: str,
        timestamp: float,
        is_animal: bool = True,
        is_human: bool = False,
    ):
        """
        Manually trigger or backdate a zone alert timestamp.
        By default, sets the animal siren cooldown (without suppressing human notifications).
        """
        self._zone_last_alert[zone_id] = timestamp
        if is_animal:
            self._zone_last_animal_alert[zone_id] = timestamp
        if is_human:
            self._zone_last_human_alert[zone_id] = timestamp

    def set_zone_human_cooldown(self, zone_id: str, timestamp: float):
        """Manually trigger or backdate a human notification timestamp."""
        self._zone_last_human_alert[zone_id] = timestamp

    def register_zone(self, zone: ZoneConfig):
        """Register a new zone or overwrite an existing one."""
        self.village_manager.register_zone(zone)
        self.zones = self.village_manager.zones

    def resolve_zone_for_class(
        self,
        class_name: str,
        detection_box: Optional[Tuple[int, int, int, int]] = None,
        preferred_zone: Optional[Union[str, ZoneConfig]] = None,
    ) -> ZoneConfig:
        """
        Determines the appropriate Zone for a detection.
        If an explicit zone is given, returns it.
        Otherwise, classifies automatically based on class semantics.
        """
        if preferred_zone is not None:
            if isinstance(preferred_zone, ZoneConfig):
                return preferred_zone
            z = self.village_manager.get_zone(preferred_zone)
            if z:
                return z

        # Spatial test if spatial bounds configured
        if detection_box is not None:
            cx = (detection_box[0] + detection_box[2]) / 2.0
            cy = (detection_box[1] + detection_box[3]) / 2.0
            for z in self.zones.values():
                if z.spatial_bounds is not None:
                    bx1, by1, bx2, by2 = z.spatial_bounds
                    if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                        return z

        # Default semantic zone classification
        clean = class_name.strip().lower()
        if clean in HUMAN_CLASSES:
            return self.restricted_zone
        return self.animal_zone

    def evaluate(
        self,
        detection: Union[Detection, Dict[str, Any]],
        camera_id: Optional[str] = None,
        zone: Optional[Union[str, ZoneConfig]] = None,
        village_id: Optional[str] = None,
        current_time: Optional[float] = None,
    ) -> RuleDecision:
        """
        Evaluates a detection against all configured rules:
        - Class normalization
        - Confidence threshold
        - Camera & Village inheritance
        - Deduplication (Track ID & Spatial/Temporal IoU)
        - Cooldown checks
        - Risk assessment
        - Village-specific laptop siren activation
        - Event logging
        """
        now = current_time if current_time is not None else time.time()

        # 1. Normalize detection fields
        if isinstance(detection, dict):
            raw_class = detection.get("class_name") or detection.get("class") or "Unknown"
            confidence = float(detection.get("confidence", 0.0))
            box = detection.get("box")
            track_id = detection.get("track_id")
            timestamp = float(detection.get("timestamp", now))
            det_cam_id = detection.get("camera_id")
        else:
            raw_class = detection.class_name
            confidence = detection.confidence
            box = detection.box
            track_id = detection.track_id
            timestamp = detection.timestamp
            det_cam_id = getattr(detection, "camera_id", None)

        canonical_class = normalize_class_name(raw_class)
        clean_key = raw_class.strip().lower()

        # 2. Resolve Camera, Village, and Zone Association
        active_cam_id = camera_id or det_cam_id or self.village_manager.active_camera_id or "CAM-001"
        camera_cfg = self.village_manager.get_camera(active_cam_id)

        # Village Association
        target_vil_id = village_id or (camera_cfg.village_id if camera_cfg else None)
        village_cfg = self.village_manager.get_village(target_vil_id) if target_vil_id else None

        # Zone Association
        if zone is not None:
            active_zone = self.resolve_zone_for_class(canonical_class, box, preferred_zone=zone)
        elif camera_cfg and camera_cfg.zone_id:
            active_zone = self.village_manager.get_zone(camera_cfg.zone_id) or self.resolve_zone_for_class(canonical_class, box)
        else:
            active_zone = self.resolve_zone_for_class(canonical_class, box)

        # 3. Rule: Check Excluded Classes (e.g. Peacock)
        if clean_key in EXCLUDED_CLASSES or canonical_class.lower() == "peacock":
            reason = "Excluded class"
            self.event_logger.log(
                detection_class=canonical_class,
                confidence=confidence,
                camera_id=active_cam_id,
                village_id=village_cfg.id if village_cfg else None,
                zone_id=active_zone.id if active_zone else None,
                risk_level="LOW",
                action_taken=RuleAction.IGNORED.value,
                siren_config_selected=None,
                siren_playback_status="NOT_ACTIVATED_PEACOCK",
                village_name=village_cfg.name if village_cfg else None,
                zone_name=active_zone.name if active_zone else None,
                timestamp=now,
            )
            return RuleDecision(
                is_event=False,
                action=RuleAction.IGNORED,
                class_name=canonical_class,
                confidence=confidence,
                camera_id=active_cam_id,
                village_id=village_cfg.id if village_cfg else None,
                village_name=village_cfg.name if village_cfg else None,
                zone_id=active_zone.id if active_zone else None,
                zone_name=active_zone.name if active_zone else None,
                reason=reason,
                timestamp=now,
            )

        # 4. Rule: Check Supported Classes
        is_animal = clean_key in ANIMAL_CLASSES or canonical_class in {
            "Elephant", "Deer", "Leopard", "Wild_boar"
        }
        is_human = clean_key in HUMAN_CLASSES or canonical_class == "Human"

        if not is_animal and not is_human:
            reason = "Unsupported class"
            return RuleDecision(
                is_event=False,
                action=RuleAction.IGNORED,
                class_name=canonical_class,
                confidence=confidence,
                camera_id=active_cam_id,
                village_id=village_cfg.id if village_cfg else None,
                village_name=village_cfg.name if village_cfg else None,
                zone_id=active_zone.id if active_zone else None,
                zone_name=active_zone.name if active_zone else None,
                reason=reason,
                timestamp=now,
            )

        # 5. Rule: Confidence Threshold Verification
        threshold = (
            active_zone.confidence_threshold
            if active_zone and active_zone.confidence_threshold is not None
            else self.default_confidence_threshold
        )
        if confidence < threshold:
            reason = "Confidence below threshold"
            return RuleDecision(
                is_event=False,
                action=RuleAction.IGNORED,
                class_name=canonical_class,
                confidence=confidence,
                camera_id=active_cam_id,
                village_id=village_cfg.id if village_cfg else None,
                village_name=village_cfg.name if village_cfg else None,
                zone_id=active_zone.id if active_zone else None,
                zone_name=active_zone.name if active_zone else None,
                reason=reason,
                timestamp=now,
            )

        # 6. Rule: Zone-Type Legacy Compatibility Check (Animal Zone vs Restricted Zone strict separation)
        if hasattr(active_zone, "zone_type"):
            if (active_zone.id == "zone-animal-default" or active_zone.name == "Animal Zone") and not is_animal:
                return RuleDecision(
                    is_event=False,
                    action=RuleAction.IGNORED,
                    class_name=canonical_class,
                    confidence=confidence,
                    camera_id=active_cam_id,
                    village_id=village_cfg.id if village_cfg else None,
                    village_name=village_cfg.name if village_cfg else None,
                    zone_id=active_zone.id,
                    zone_name=active_zone.name,
                    reason=f"Wrong class for {active_zone.name} (Animal Zone expects wildlife)",
                    timestamp=now,
                )
            if (active_zone.id == "zone-restricted-default" or active_zone.name == "Restricted Zone") and not is_human:
                return RuleDecision(
                    is_event=False,
                    action=RuleAction.IGNORED,
                    class_name=canonical_class,
                    confidence=confidence,
                    camera_id=active_cam_id,
                    village_id=village_cfg.id if village_cfg else None,
                    village_name=village_cfg.name if village_cfg else None,
                    zone_id=active_zone.id,
                    zone_name=active_zone.name,
                    reason=f"Wrong class for {active_zone.name} (Restricted Zone expects human activity)",
                    timestamp=now,
                )

        # 7. Rule: Duplicate Detection Prevention (Object-level suppression)
        # 7a. Tracking ID Deduplication
        if track_id is not None:
            last_track_time = self._track_last_alert.get(track_id)
            if last_track_time is not None and (now - last_track_time) < self.duplicate_window_seconds:
                return RuleDecision(
                    is_event=False,
                    action=RuleAction.IGNORED,
                    class_name=canonical_class,
                    confidence=confidence,
                    camera_id=active_cam_id,
                    village_id=village_cfg.id if village_cfg else None,
                    village_name=village_cfg.name if village_cfg else None,
                    zone_id=active_zone.id,
                    zone_name=active_zone.name,
                    reason=f"Duplicate detection suppressed (track_id {track_id} active)",
                    timestamp=now,
                )
        # 7b. Spatial / Temporal Deduplication when track_id is absent
        else:
            for past in self._recent_events:
                if past["zone_id"] == active_zone.id and past["class_name"] == canonical_class:
                    if (now - past["timestamp"]) < self.duplicate_window_seconds:
                        if box is not None and past["box"] is not None:
                            iou = compute_iou(box, past["box"])
                            if iou > 0.30:
                                return RuleDecision(
                                    is_event=False,
                                    action=RuleAction.IGNORED,
                                    class_name=canonical_class,
                                    confidence=confidence,
                                    camera_id=active_cam_id,
                                    village_id=village_cfg.id if village_cfg else None,
                                    village_name=village_cfg.name if village_cfg else None,
                                    zone_id=active_zone.id,
                                    zone_name=active_zone.name,
                                    reason="Duplicate detection suppressed",
                                    timestamp=now,
                                )
                        else:
                            return RuleDecision(
                                is_event=False,
                                action=RuleAction.IGNORED,
                                class_name=canonical_class,
                                confidence=confidence,
                                camera_id=active_cam_id,
                                village_id=village_cfg.id if village_cfg else None,
                                village_name=village_cfg.name if village_cfg else None,
                                zone_id=active_zone.id,
                                zone_name=active_zone.name,
                                reason="Duplicate detection suppressed",
                                timestamp=now,
                            )

        # 8. Rule: Alert Cooldown Check
        # Separate cooldown handling for animal siren alerts vs human notifications:
        # - Animal siren alerts enforce zone-level cooldown_seconds (default 90s).
        # - Human notifications are NEVER suppressed by animal siren cooldowns.
        # - Human notifications use a separate configurable human cooldown (default 0.0s / disabled).
        if is_animal:
            animal_cooldown = (
                active_zone.cooldown_seconds
                if active_zone and active_zone.cooldown_seconds is not None
                else self.default_cooldown_seconds
            )
            last_animal_alert = self._zone_last_animal_alert.get(active_zone.id)
            if last_animal_alert is not None and animal_cooldown > 0:
                elapsed = now - last_animal_alert
                if elapsed < animal_cooldown:
                    remaining = int(math.ceil(animal_cooldown - elapsed))
                    return RuleDecision(
                        is_event=False,
                        action=RuleAction.IGNORED,
                        class_name=canonical_class,
                        confidence=confidence,
                        camera_id=active_cam_id,
                        village_id=village_cfg.id if village_cfg else None,
                        village_name=village_cfg.name if village_cfg else None,
                        zone_id=active_zone.id,
                        zone_name=active_zone.name,
                        reason=f"Alert cooldown active ({remaining}s remaining)",
                        timestamp=now,
                    )
        elif is_human:
            human_cooldown = getattr(active_zone, "human_cooldown_seconds", None) if active_zone else None
            if human_cooldown is None:
                human_cooldown = self.default_human_cooldown_seconds

            if human_cooldown is not None and human_cooldown > 0:
                last_human_alert = self._zone_last_human_alert.get(active_zone.id)
                if last_human_alert is not None:
                    elapsed = now - last_human_alert
                    if elapsed < human_cooldown:
                        remaining = int(math.ceil(human_cooldown - elapsed))
                        return RuleDecision(
                            is_event=False,
                            action=RuleAction.IGNORED,
                            class_name=canonical_class,
                            confidence=confidence,
                            camera_id=active_cam_id,
                            village_id=village_cfg.id if village_cfg else None,
                            village_name=village_cfg.name if village_cfg else None,
                            zone_id=active_zone.id,
                            zone_name=active_zone.name,
                            reason=f"Human notification cooldown active ({remaining}s remaining)",
                            timestamp=now,
                        )

        # 9. Risk Assessment Evaluation (Module 5)
        persistence, direction = self.risk_engine.update_history(
            class_name=canonical_class,
            zone_id=active_zone.id,
            box=box,
            track_id=track_id,
            timestamp=now,
        )
        risk_result = self.risk_engine.assess_risk(
            species=canonical_class,
            zone_type=active_zone.zone_type.value if hasattr(active_zone, "zone_type") else str(active_zone),
            confidence=confidence,
            persistence_count=persistence,
            movement_direction=direction,
            zone_name=active_zone.name,
        )

        # 10. Action & Siren Logic (Module 6)
        if is_animal:
            action = RuleAction.ANIMAL_ALERT_REQUIRED
            action_text = "Animal alert required"

            # Trigger Village-Specific Siren
            if village_cfg:
                siren_res = self.siren_service.trigger_siren_for_village(
                    village=village_cfg,
                    track_id=track_id,
                    current_time=now,
                )
                siren_status = siren_res.status.value
                siren_pattern = siren_res.pattern_description
            else:
                siren_status = SirenStatus.UNKNOWN_VILLAGE.value
                siren_pattern = None

        else:
            # Human Detection: MUST NOT activate siren
            action = RuleAction.HUMAN_NOTIFICATION_REQUIRED
            action_text = "Human detection recorded"
            siren_status = "NOT_ACTIVATED"
            siren_pattern = None

        # 11. Update Internal States
        if is_animal:
            self._zone_last_animal_alert[active_zone.id] = now
        else:
            self._zone_last_human_alert[active_zone.id] = now
        self._zone_last_alert[active_zone.id] = now
        if track_id is not None:
            self._track_last_alert[track_id] = now

        self._recent_events.append({
            "class_name": canonical_class,
            "zone_id": active_zone.id,
            "box": box,
            "timestamp": now,
        })
        cutoff = now - max(self.duplicate_window_seconds, 60.0)
        self._recent_events = [ev for ev in self._recent_events if ev["timestamp"] >= cutoff]

        # 12. Record in Event Log (Module 7)
        event_rec = self.event_logger.log(
            detection_class=canonical_class,
            confidence=confidence,
            camera_id=active_cam_id,
            village_id=village_cfg.id if village_cfg else (target_vil_id or None),
            zone_id=active_zone.id if active_zone else None,
            risk_level=risk_result.level.value,
            action_taken=action.value,
            siren_config_selected=siren_pattern,
            siren_playback_status=siren_status,
            village_name=village_cfg.name if village_cfg else None,
            zone_name=active_zone.name if active_zone else None,
            timestamp=now,
            details={
                "risk_score": risk_result.score,
                "persistence_count": persistence,
                "movement_direction": direction,
                "box": box,
                "track_id": track_id,
            },
        )

        return RuleDecision(
            is_event=True,
            action=action,
            class_name=canonical_class,
            confidence=confidence,
            camera_id=active_cam_id,
            village_id=village_cfg.id if village_cfg else (target_vil_id or None),
            village_name=village_cfg.name if village_cfg else None,
            zone_id=active_zone.id if active_zone else None,
            zone_name=active_zone.name if active_zone else None,
            risk_level=risk_result.level.value,
            risk_score=risk_result.score,
            action_text=action_text,
            siren_pattern=siren_pattern,
            siren_status=siren_status,
            event_id=event_rec.event_id,
            timestamp=now,
        )


# Global default instance
default_engine = DetectionRuleEngine()
