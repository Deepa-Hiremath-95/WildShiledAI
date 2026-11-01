"""
WildShield AI - Alert Management Engine (Phase 5 Hardened)
==========================================================
Coordinates detection evaluation, risk classification, independent cooldowns,
siren deterrence, and alert lifecycle persistence across the entire system.

Strict Operational Invariants:
1. HUMAN events NEVER activate acoustic sirens under any circumstance.
2. HUMAN notifications follow independent cooldown handling and NEVER suppress
   or get suppressed by ongoing 90-second animal siren cooldowns.
3. ANIMAL detections strictly enforce the 90-second siren cooldown.
4. Excluded species (Peacock) are excluded from triggering conflict alerts.
5. All detections are persisted to the database for historical auditability.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app import models
from app.services import sms_service, hardware_service

logger = logging.getLogger("wildshield.alert_engine")

EXCLUDED_SPECIES_DEFAULT = ["peacock"]


class AlertResult:
    def __init__(self, alert: Optional[models.Alert], detection: Optional[models.Detection], reason: str):
        self.alert = alert
        self.detection = detection
        self.reason = reason  # "triggered" | "below_threshold" | "cooldown" | "excluded_species" | "duplicate"


def _get_system_setting(db: Session, key: str, default: any) -> any:
    """Retrieve persistent setting from DB with fallback to default."""
    try:
        setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
        if setting and setting.value is not None:
            if isinstance(default, (int, float, bool)):
                return type(default)(setting.value)
            elif isinstance(default, list):
                return json.loads(setting.value)
            return setting.value
    except Exception as e:
        logger.debug(f"Could not read setting {key}: {e}")
    return default


def _in_animal_cooldown(camera: models.Camera, cooldown_seconds: int) -> bool:
    """Checks whether the camera node is currently in an active animal siren cooldown."""
    if not camera.last_alert_at:
        return False
    return datetime.utcnow() < camera.last_alert_at + timedelta(seconds=cooldown_seconds)


def _in_human_cooldown(camera: models.Camera, cooldown_seconds: int) -> bool:
    """Checks whether the camera node is in a human notification duplicate window."""
    if not camera.last_human_alert_at:
        return False
    return datetime.utcnow() < camera.last_human_alert_at + timedelta(seconds=cooldown_seconds)


def _calculate_risk(
    event_type: models.EventType,
    species: Optional[str],
    confidence: float,
    boundary_crossing: bool,
    zone_type: models.ZoneType
) -> str:
    """Calculates risk level according to species, confidence, zone, and movement."""
    species_lower = (species or "").lower()

    if event_type == models.EventType.PERSON_DETECTED or species_lower == "human":
        if zone_type == models.ZoneType.RESTRICTED or boundary_crossing:
            return "high" if confidence >= 0.85 else "medium"
        return "medium" if confidence >= 0.70 else "low"

    # Animal threat classification
    if species_lower in {"leopard", "tiger", "lion"}:
        return "critical"
    if species_lower == "elephant":
        return "critical" if (confidence >= 0.90 or boundary_crossing) else "high"
    if species_lower in {"wild_boar", "wild boar", "boar"}:
        return "high" if boundary_crossing else "medium"
    if species_lower == "deer":
        return "medium" if boundary_crossing else "low"

    if confidence >= 0.90 or boundary_crossing:
        return "critical" if confidence >= 0.90 else "high"
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.50:
        return "medium"
    return "low"


def _format_title(event_type: models.EventType, species: Optional[str], location_name: str) -> str:
    if event_type == models.EventType.PERSON_DETECTED or (species or "").lower() == "human":
        return f"Human activity detected — {location_name}"
    label = species or "Wildlife"
    return f"{label} movement detected — {location_name}"


def process_detection(
    db: Session,
    camera: models.Camera,
    zone: models.Zone,
    event_type: models.EventType,
    confidence: float,
    snapshot_path: Optional[str],
    species: Optional[str] = None,
    movement_direction: Optional[str] = None,
    boundary_crossing: bool = False,
) -> AlertResult:
    """
    Core detection evaluation pipeline.
    Always creates a Detection record.
    Evaluates rules, applies separate cooldowns, and creates Alert if warranted.
    """
    now = datetime.utcnow()
    species_name = species or ("Human" if event_type == models.EventType.PERSON_DETECTED else "Wildlife")
    species_lower = species_name.lower()
    village_id = camera.village_id or (zone.village_id if zone else None)

    # 1. Check excluded species (e.g. Peacock)
    excluded = _get_system_setting(db, "excluded_species", EXCLUDED_SPECIES_DEFAULT)
    if species_lower in [s.lower() for s in excluded]:
        logger.info(f"Ignoring excluded species '{species_name}' at camera {camera.id}")
        det = models.Detection(
            camera_id=camera.id,
            zone_id=zone.id,
            village_id=village_id,
            event_type=event_type,
            species=species_name,
            confidence=confidence,
            movement_direction=movement_direction,
            boundary_crossing=boundary_crossing,
            risk_level="low",
            action_taken="IGNORED (Excluded Species)",
            siren_triggered=False,
            snapshot_path=snapshot_path,
            created_at=now
        )
        db.add(det)
        db.commit()
        db.refresh(det)
        return AlertResult(None, det, "excluded_species")

    # 2. Check confidence floor (zone threshold takes precedence, else global default)
    min_conf = zone.confidence_threshold if zone.confidence_threshold is not None else _get_system_setting(db, "min_confidence", 0.60)
    if confidence < min_conf:
        logger.info(f"Detection below confidence threshold ({confidence:.2f} < {min_conf:.2f})")
        det = models.Detection(
            camera_id=camera.id,
            zone_id=zone.id,
            village_id=village_id,
            event_type=event_type,
            species=species_name,
            confidence=confidence,
            movement_direction=movement_direction,
            boundary_crossing=boundary_crossing,
            risk_level="low",
            action_taken=f"IGNORED (Confidence {confidence:.2f} < {min_conf:.2f})",
            siren_triggered=False,
            snapshot_path=snapshot_path,
            created_at=now
        )
        db.add(det)
        db.commit()
        db.refresh(det)
        return AlertResult(None, det, "below_threshold")

    # 3. Determine if Human vs Animal
    is_human = (event_type == models.EventType.PERSON_DETECTED or species_lower == "human")

    # 4. Independent Cooldown Enforcement
    if is_human:
        # Human duplicate suppression window (default 10s)
        human_cd = _get_system_setting(db, "human_notification_cooldown_seconds", 10)
        if _in_human_cooldown(camera, human_cd):
            logger.info(f"Camera {camera.id}: Human detection duplicate suppressed ({human_cd}s window)")
            det = models.Detection(
                camera_id=camera.id,
                zone_id=zone.id,
                village_id=village_id,
                event_type=event_type,
                species=species_name,
                confidence=confidence,
                movement_direction=movement_direction,
                boundary_crossing=boundary_crossing,
                risk_level="medium",
                action_taken="SUPPRESSED (Human Duplicate Cooldown Active)",
                siren_triggered=False,
                snapshot_path=snapshot_path,
                created_at=now
            )
            db.add(det)
            db.commit()
            db.refresh(det)
            return AlertResult(None, det, "cooldown")
    else:
        # Animal siren cooldown (default 90s)
        animal_cd = zone.cooldown_seconds if zone.cooldown_seconds is not None else _get_system_setting(db, "animal_siren_cooldown_seconds", 90)
        if _in_animal_cooldown(camera, animal_cd):
            logger.info(f"Camera {camera.id}: Animal detection siren cooldown active ({animal_cd}s window)")
            det = models.Detection(
                camera_id=camera.id,
                zone_id=zone.id,
                village_id=village_id,
                event_type=event_type,
                species=species_name,
                confidence=confidence,
                movement_direction=movement_direction,
                boundary_crossing=boundary_crossing,
                risk_level="medium",
                action_taken=f"SUPPRESSED (Animal Siren Cooldown {animal_cd}s Active)",
                siren_triggered=False,
                snapshot_path=snapshot_path,
                created_at=now
            )
            db.add(det)
            db.commit()
            db.refresh(det)
            return AlertResult(None, det, "cooldown")

    # 5. Risk Assessment & Action
    risk_level = _calculate_risk(event_type, species_name, confidence, boundary_crossing, zone.type)
    title = _format_title(event_type, species_name, zone.name)

    # 6. Siren Deterrence Policy
    siren_activated = False
    action_taken = ""

    if is_human:
        # STRICT RULE: Humans NEVER activate acoustic sirens under ANY circumstance
        siren_activated = False
        action_taken = "HUMAN_NOTIFICATION_REQUIRED (Siren Never Activated)"
        camera.last_human_alert_at = now
    else:
        # Animal detection: activate siren if in Animal/Buffer zone
        if zone.type == models.ZoneType.ANIMAL:
            duration = zone.siren_duration_seconds or 45
            siren_activated = hardware_service.activate_siren(zone.id, duration)
            zone.siren_status = siren_activated
            zone.siren_activated_at = now
            zone.siren_reason = title
            action_taken = f"Animal Siren Activated ({duration}s duration, 90s cooldown)"
        else:
            siren_activated = False
            action_taken = "Restricted zone animal logged"
        camera.last_alert_at = now

    # 7. Create Alert Record
    alert = models.Alert(
        zone_id=zone.id,
        camera_id=camera.id,
        village_id=village_id,
        event_type=event_type,
        confidence=confidence,
        snapshot_path=snapshot_path,
        siren_activated=siren_activated,
        sms_sent=False,
        species=species_name,
        movement_direction=movement_direction,
        boundary_crossing=boundary_crossing,
        risk_level=risk_level,
        status="active",
        title=title,
        read=False,
        created_at=now,
    )
    db.add(alert)
    db.flush()

    # 8. Create Detection Record Linked to Alert
    det = models.Detection(
        id=f"det-{alert.id}",
        camera_id=camera.id,
        zone_id=zone.id,
        village_id=village_id,
        event_type=event_type,
        species=species_name,
        confidence=confidence,
        movement_direction=movement_direction,
        boundary_crossing=boundary_crossing,
        risk_level=risk_level,
        action_taken=action_taken,
        siren_triggered=siren_activated,
        snapshot_path=snapshot_path,
        alert_id=alert.id,
        created_at=now,
    )
    db.add(det)

    # 9. Optional Authority Dispatch Message (Mock)
    contact_numbers = [zc.contact.phone_number for zc in zone.contacts] if zone.contacts else []
    if contact_numbers:
        msg = sms_service.alert_message(zone.name, event_type.value, confidence, now.isoformat())
        alert.sms_sent = sms_service.send_sms(contact_numbers, msg)

    camera.last_heartbeat = now
    camera.is_online = True

    db.commit()
    db.refresh(alert)
    db.refresh(det)

    logger.info(f"Alert {alert.id} created for {species_name} ({risk_level.upper()}) | Siren: {siren_activated}")
    return AlertResult(alert, det, "triggered")
