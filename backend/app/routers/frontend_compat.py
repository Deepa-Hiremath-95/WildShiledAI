"""
WildShield AI - Frontend Compatibility Layer
============================================
Ensures seamless backward compatibility for all existing dashboard routes:
- /api/detections
- /api/active-alerts
- /api/villages
- /api/sirens
- /api/map-data
- /api/analytics
- /api/sirens/{id}/activate
- /api/sirens/{id}/deactivate
"""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import get_current_user
from app.services import hardware_service
from app.services.ws_manager import manager
from app.routers.villages import list_villages as get_villages_impl

router = APIRouter(tags=["frontend-compat"])


def _fmt_alert_for_frontend(a: models.Alert) -> dict:
    recipients = ["Forest Officers"]
    if a.zone and a.zone.type == models.ZoneType.ANIMAL:
        recipients += ["Police", "Rescue/Security Team"]
    else:
        recipients += ["Rangers"]

    is_human = (a.event_type == models.EventType.PERSON_DETECTED or (a.species or "").lower() == "human")
    if is_human:
        action_taken = "Human notification recorded • Siren never activated"
    else:
        action_taken = f"Village siren {'ON' if a.siren_activated else 'not triggered'} • Forest officer alerted"

    sms_status = (
        "Delivered (Mock Provider)" if a.sms_sent
        else ("Failed" if a.created_at else "Pending")
    )

    zone_name = a.zone.name if a.zone else "Zone A"
    vil_name = a.village.name if (getattr(a, "village", None) and isinstance(getattr(a.village, "name", None), str)) else (zone_name.split("—")[0].strip() if "—" in zone_name else zone_name)

    return {
        "id": a.id,
        "title": a.title,
        "riskLevel": a.risk_level,
        "status": a.status,
        "read": bool(getattr(a, "read", False)),
        "isRead": bool(getattr(a, "read", False)),
        "confidence": a.confidence,
        "detectedObject": a.species or ("Human" if is_human else "Animal"),
        "speciesOrHuman": (
            f"Human • {a.species or 'Person'}" if is_human
            else f"Animal • {a.species or 'Unclassified'}"
        ),
        "location": a.camera.name if a.camera else zone_name,
        "zone": zone_name,
        "village": vil_name,
        "movementDirection": a.movement_direction or "Unknown",
        "actionTaken": action_taken,
        "timestamp": a.created_at.isoformat(),
        "recipients": recipients,
        "sirenActivated": bool(a.siren_activated),
        "smsSent": bool(a.sms_sent),
        "smsDeliveryStatus": sms_status,
        "eventType": a.event_type.value if hasattr(a.event_type, "value") else str(a.event_type),
    }


def _fmt_detection_from_det(d: models.Detection) -> dict:
    is_human = (d.event_type == models.EventType.PERSON_DETECTED or (d.species or "").lower() == "human")
    zone_name = d.zone.name if d.zone else "Zone A"
    vil_name = d.village.name if (getattr(d, "village", None) and isinstance(getattr(d.village, "name", None), str)) else (zone_name.split("—")[0].strip() if "—" in zone_name else zone_name)
    cam_name = d.camera.name if d.camera else d.camera_id

    return {
        "id": d.id,
        "type": "human" if is_human else "animal",
        "species": d.species or ("Human" if is_human else "Unclassified"),
        "classification": d.species or ("Human" if is_human else "Unclassified"),
        "confidence": d.confidence,
        "location": cam_name,
        "movementDirection": d.movement_direction or "Unknown",
        "boundaryCrossing": bool(d.boundary_crossing),
        "riskLevel": d.risk_level or "low",
        "affectedVillage": vil_name,
        "sirenStatus": "on" if d.siren_triggered else "off",
        "timestamp": d.created_at.isoformat(),
        "imageLabel": "Detection image" if d.snapshot_path else "No image captured",
        "snapshotUrl": d.snapshot_path,
    }


def _fmt_detection_from_alert(a: models.Alert) -> dict:
    is_human = (a.event_type == models.EventType.PERSON_DETECTED or (a.species or "").lower() == "human")
    zone_name = a.zone.name if a.zone else "Zone A"
    cam_name = a.camera.name if a.camera else zone_name

    return {
        "id": a.id,
        "type": "human" if is_human else "animal",
        "species": a.species or ("Human" if is_human else "Unclassified"),
        "classification": a.species or ("Human" if is_human else "Unclassified"),
        "confidence": a.confidence,
        "location": cam_name,
        "movementDirection": a.movement_direction or "Unknown",
        "boundaryCrossing": bool(a.boundary_crossing),
        "riskLevel": a.risk_level,
        "affectedVillage": zone_name,
        "sirenStatus": "on" if a.siren_activated else "off",
        "timestamp": a.created_at.isoformat(),
        "imageLabel": "Detection image" if a.snapshot_path else "No image captured",
        "snapshotUrl": a.snapshot_path,
    }


# Backward-compatible alias for existing tests
_fmt_detection_for_frontend = _fmt_detection_from_alert


@router.get("/detections")
def get_detections(db: Session = Depends(get_db)):
    """
    Returns latest detections from the detections historical table.
    Falls back to alerts table if detections table is empty.
    """
    dets = db.query(models.Detection).order_by(models.Detection.created_at.desc()).limit(100).all()
    if dets:
        return [_fmt_detection_from_det(d) for d in dets]

    alerts = db.query(models.Alert).order_by(models.Alert.created_at.desc()).limit(50).all()
    return [_fmt_detection_from_alert(a) for a in alerts]


@router.get("/active-alerts")
def get_active_alerts(db: Session = Depends(get_db)):
    """Returns active and recent alerts."""
    alerts = db.query(models.Alert).order_by(models.Alert.created_at.desc()).limit(50).all()
    return [_fmt_alert_for_frontend(a) for a in alerts]


@router.get("/villages")
def get_villages(db: Session = Depends(get_db)):
    """Returns villages list matching frontend api-service contract."""
    return get_villages_impl(db)


@router.get("/sirens")
def get_sirens(db: Session = Depends(get_db)):
    """Returns acoustic siren states for all animal monitoring zones."""
    zones = db.query(models.Zone).filter(models.Zone.type == models.ZoneType.ANIMAL).all()
    is_mock = getattr(hardware_service, "MOCK_MODE", True)
    return [
        {
            "id": z.id,
            "name": f"Siren — {z.name}",
            "currentStatus": "on" if z.siren_status else "off",
            "zoneStatus": "At Risk" if z.siren_status else "Safe",
            "village": z.village.name if z.village else z.name,
            "connected": True,
            "isHardwareConnected": not is_mock,
            "hardwareMode": "simulated" if is_mock else "gpio_relay",
            "hardwareStatusLabel": "Simulated Controller (Mock Mode)" if is_mock else "Hardware Relay Armed (GPIO 18)",
            "lastActivatedAt": z.siren_activated_at.isoformat() if z.siren_activated_at else None,
            "activationReason": z.siren_reason or "No active threat",
        }
        for z in zones
    ]


@router.post("/sirens/{zone_id}/activate")
async def activate_siren(zone_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Manually activates an acoustic siren."""
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Siren/zone not found")

    ok = hardware_service.activate_siren(zone.id, zone.siren_duration_seconds)
    zone.siren_status = ok
    zone.siren_activated_at = datetime.utcnow()
    zone.siren_reason = "Manually activated by operator"

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="SIREN_ACTIVATED",
        resource_type="siren",
        resource_id=zone.id,
        details=json.dumps({"zone": zone.name}),
    )
    db.add(audit)
    db.commit()

    await manager.broadcast_siren(zone.id, True, zone.siren_reason)

    return {
        "id": zone.id,
        "name": f"Siren — {zone.name}",
        "currentStatus": "on" if zone.siren_status else "off",
        "zoneStatus": "At Risk" if zone.siren_status else "Safe",
        "village": zone.village.name if zone.village else zone.name,
        "connected": True,
        "lastActivatedAt": zone.siren_activated_at.isoformat(),
        "activationReason": zone.siren_reason,
    }


@router.post("/sirens/{zone_id}/deactivate")
async def deactivate_siren(zone_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Manually halts an acoustic siren."""
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Siren/zone not found")

    hardware_service.deactivate_siren(zone.id)
    zone.siren_status = False
    zone.siren_reason = "Manually deactivated by operator"

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="SIREN_DEACTIVATED",
        resource_type="siren",
        resource_id=zone.id,
        details=json.dumps({"zone": zone.name}),
    )
    db.add(audit)
    db.commit()

    await manager.broadcast_siren(zone.id, False, zone.siren_reason)

    return {
        "id": zone.id,
        "name": f"Siren — {zone.name}",
        "currentStatus": "off",
        "zoneStatus": "Safe",
        "village": zone.village.name if zone.village else zone.name,
        "connected": True,
        "lastActivatedAt": zone.siren_activated_at.isoformat() if zone.siren_activated_at else None,
        "activationReason": zone.siren_reason,
    }


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """Returns aggregated incident analytics across species, risk levels, and real timeframes."""
    alerts = db.query(models.Alert).all()
    detections = db.query(models.Detection).all()

    species_map: dict[str, int] = {}
    for a in alerts:
        sp = a.species or ("Human" if a.event_type == models.EventType.PERSON_DETECTED else "Other")
        species_map[sp] = species_map.get(sp, 0) + 1

    # Include detections to ensure comprehensive species count
    for d in detections:
        sp = d.species or ("Human" if d.event_type == models.EventType.PERSON_DETECTED else "Other")
        if sp not in species_map:
            species_map[sp] = 0

    species_counts = [
        {"name": k, "count": v, "label": k, "value": v}
        for k, v in sorted(species_map.items(), key=lambda x: x[1], reverse=True)
    ]

    risk_map = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in alerts:
        rl = (a.risk_level or "medium").lower()
        if rl in risk_map:
            risk_map[rl] += 1

    risk_levels = [
        {"level": "low", "count": risk_map["low"], "label": "Low", "value": risk_map["low"]},
        {"level": "medium", "count": risk_map["medium"], "label": "Medium", "value": risk_map["medium"]},
        {"level": "high", "count": risk_map["high"], "label": "High", "value": risk_map["high"]},
        {"level": "critical", "count": risk_map["critical"], "label": "Critical", "value": risk_map["critical"]},
    ]

    # Compute actual chronological trend across 6 real date intervals
    latest_record = db.query(models.Alert).order_by(models.Alert.created_at.desc()).first()
    anchor_dt = latest_record.created_at if (latest_record and latest_record.created_at) else datetime.utcnow()

    wildlife_trend = [0] * 6
    human_trend = [0] * 6
    siren_trend = [0] * 6

    for a in alerts:
        if a.created_at:
            day_diff = (anchor_dt.date() - a.created_at.date()).days
            if 0 <= day_diff < 6:
                idx = 5 - day_diff
                if a.event_type == models.EventType.ANIMAL_DETECTED:
                    wildlife_trend[idx] += 1
                elif a.event_type == models.EventType.PERSON_DETECTED:
                    human_trend[idx] += 1
                if a.siren_activated:
                    siren_trend[idx] += 1

    # Real movement directions from alerts and detections
    dir_map: dict[str, int] = {}
    for a in alerts:
        if a.movement_direction:
            d_norm = a.movement_direction.strip().title()
            dir_map[d_norm] = dir_map.get(d_norm, 0) + 1
    for d in detections:
        if d.movement_direction:
            d_norm = d.movement_direction.strip().title()
            dir_map[d_norm] = dir_map.get(d_norm, 0) + 1

    movement_directions = [
        {"label": k, "value": v}
        for k, v in sorted(dir_map.items(), key=lambda x: x[1], reverse=True)
    ]
    if not movement_directions:
        movement_directions = [{"label": "Perimeter Buffer", "value": len(alerts) or 1}]

    confirmed = sum(1 for a in alerts if a.siren_activated or (a.risk_level or "").lower() in ("high", "critical"))
    low_risk = sum(1 for a in alerts if (a.risk_level or "").lower() == "low" and not a.siren_activated)

    return {
        "speciesCounts": species_counts or [{"name": "Elephant", "count": 0, "label": "Elephant", "value": 0}],
        "riskLevels": risk_levels,
        "wildlifeIntrusions": wildlife_trend,
        "humanIntrusions": human_trend,
        "sirenActivations": siren_trend,
        "totalAlerts": len(alerts),
        "falseAlarmStats": {
            "falseAlarms": low_risk,
            "confirmedIntrusions": confirmed,
        },
        "movementDirections": movement_directions,
    }


@router.get("/map-data")
def get_map_data(db: Session = Depends(get_db)):
    """Returns spatial coordinates and threat vector for vector map views."""
    zones = db.query(models.Zone).all()
    latest_crit = (
        db.query(models.Alert)
        .filter(models.Alert.risk_level.in_(["high", "critical"]))
        .order_by(models.Alert.created_at.desc())
        .first()
    )

    threat = {
        "animal": latest_crit.species if latest_crit else "None",
        "confidence": latest_crit.confidence if latest_crit else 0.0,
        "currentLocation": latest_crit.zone.name if (latest_crit and latest_crit.zone) else "Sector Quiet",
        "movingToward": "Village Perimeter",
        "distance": "1.2 km (Zone A Buffer)",
        "riskLevel": latest_crit.risk_level if latest_crit else "low",
        "siren": latest_crit.siren_activated if latest_crit else False,
    }

    zones_out = [
        {
            "id": z.id,
            "name": z.name,
            "type": z.type.value if hasattr(z.type, "value") else str(z.type),
            "lat": z.latitude,
            "lng": z.longitude,
            "sirenStatus": z.siren_status,
        }
        for z in zones
    ]

    return {"threat": threat, "zones": zones_out}
