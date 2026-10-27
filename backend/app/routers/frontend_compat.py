"""
This router exists purely to match the shapes that frontend/api-service.js already
expects (/detections, /active-alerts, /villages, /sirens, /map-data, /analytics,
/sirens/{id}/activate|deactivate). The frontend was built first against a mock API —
rather than rewrite it, the backend speaks its language here so the existing pages work
unmodified once useMock is flipped to false.

"Village" in the frontend maps 1:1 to a Zone here. "Siren" maps 1:1 to a Zone's siren
state. This keeps one source of truth (the PRD's Zone/Camera/Alert model in models.py)
instead of maintaining two parallel data models.

Endpoints here are intentionally left unauthenticated to match the current frontend,
which does not send an Authorization header yet. Before a real deployment, add the same
get_current_user dependency used in the other routers once the frontend's login flow
(profile.html / security.html) is wired to POST /auth/login and store the token.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth import get_current_user
from app.services import hardware_service

router = APIRouter(tags=["frontend-compat"])


def _risk_badge(risk_level: str) -> str:
    return risk_level  # already low|medium|high|critical, matches frontend CSS classes


def _fmt_alert_for_frontend(a: models.Alert) -> dict:
    recipients = ["Forest Officers"]
    if a.zone.type == models.ZoneType.ANIMAL:
        recipients += ["Police", "Rescue/Security Team"]
    else:
        recipients += ["Rangers"]

    action_taken = (
        f"Village siren {'ON' if a.siren_activated else 'not triggered'} • Forest officer alerted"
        if a.zone.type == models.ZoneType.ANIMAL
        else "Forest team notified discreetly • Monitoring continued"
    )

    sms_status = (
        "Delivered (Mock Provider)" if a.sms_sent
        else ("Failed" if a.created_at else "Pending")
    )

    return {
        "id": a.id,
        "title": a.title,
        "riskLevel": a.risk_level,
        "status": a.status,
        "read": bool(getattr(a, "read", False)),
        "isRead": bool(getattr(a, "read", False)),
        "confidence": a.confidence,
        "detectedObject": a.species or ("Human" if a.event_type == models.EventType.PERSON_DETECTED else "Animal"),
        "speciesOrHuman": (
            f"Human • {a.species}" if a.event_type == models.EventType.PERSON_DETECTED
            else f"Animal • {a.species or 'Unclassified'}"
        ),
        "location": a.camera.name if a.camera else a.zone.name,
        "zone": a.zone.name,
        "village": a.zone.name.split("—")[0].strip() if "—" in a.zone.name else a.zone.name,
        "movementDirection": a.movement_direction or "Unknown",
        "actionTaken": action_taken,
        "timestamp": a.created_at.isoformat(),
        "recipients": recipients,
        "sirenActivated": bool(a.siren_activated),
        "smsSent": bool(a.sms_sent),
        "smsDeliveryStatus": sms_status,
        "eventType": a.event_type.value if hasattr(a.event_type, "value") else str(a.event_type),
    }



def _fmt_detection_for_frontend(a: models.Alert) -> dict:
    return {
        "id": a.id,
        "type": "human" if a.event_type == models.EventType.PERSON_DETECTED else "animal",
        "species": a.species or ("Human" if a.event_type == models.EventType.PERSON_DETECTED else "Unclassified"),
        "classification": a.species or ("Human" if a.event_type == models.EventType.PERSON_DETECTED else "Unclassified"),
        "confidence": a.confidence,
        "location": a.camera.name if a.camera else a.zone.name,
        "movementDirection": a.movement_direction or "Unknown",
        "boundaryCrossing": a.boundary_crossing,
        "riskLevel": a.risk_level,
        "affectedVillage": a.zone.name,
        "sirenStatus": "on" if a.siren_activated else "off",
        "timestamp": a.created_at.isoformat(),
        "imageLabel": "Detection image" if a.snapshot_path else "No image captured",
        "snapshotUrl": a.snapshot_path,
    }


@router.get("/detections")
def get_detections(db: Session = Depends(get_db)):
    alerts = db.query(models.Alert).order_by(models.Alert.created_at.desc()).limit(50).all()
    return [_fmt_detection_for_frontend(a) for a in alerts]


@router.get("/active-alerts")
def get_active_alerts(db: Session = Depends(get_db)):
    alerts = db.query(models.Alert).order_by(models.Alert.created_at.desc()).limit(50).all()
    return [_fmt_alert_for_frontend(a) for a in alerts]


@router.get("/villages")
def get_villages(db: Session = Depends(get_db)):
    zones = db.query(models.Zone).all()
    out = []
    for z in zones:
        recent_critical = (
            db.query(models.Alert)
            .filter(
                models.Alert.zone_id == z.id,
                models.Alert.status == "active",
                models.Alert.risk_level.in_(["high", "critical"]),
                models.Alert.created_at >= datetime.utcnow() - timedelta(hours=2),
            )
            .first()
        )
        out.append({
            "id": z.id,
            "name": z.name,
            "zone": z.name,
            "status": "at-risk" if (recent_critical or z.siren_status) else "safe",
            "sirenId": z.id,
            "sirenStatus": "on" if z.siren_status else "off",
            "lat": z.latitude,
            "lng": z.longitude,
            "latitude": z.latitude,
            "longitude": z.longitude,
        })
    return out


@router.get("/sirens")
def get_sirens(db: Session = Depends(get_db)):
    zones = db.query(models.Zone).filter(models.Zone.type == models.ZoneType.ANIMAL).all()
    is_mock = getattr(hardware_service, "MOCK_MODE", True)
    return [
        {
            "id": z.id,
            "name": f"Siren — {z.name}",
            "currentStatus": "on" if z.siren_status else "off",
            "zoneStatus": "At Risk" if z.siren_status else "Safe",
            "village": z.name,
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
def activate_siren(zone_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Siren/zone not found")
    ok = hardware_service.activate_siren(zone.id, zone.siren_duration_seconds)
    zone.siren_status = ok
    zone.siren_activated_at = datetime.utcnow()
    zone.siren_reason = "Manually activated by operator"
    db.commit()
    return {
        "id": zone.id,
        "name": f"Siren — {zone.name}",
        "currentStatus": "on" if zone.siren_status else "off",
        "zoneStatus": "At Risk" if zone.siren_status else "Safe",
        "village": zone.name,
        "connected": True,
        "lastActivatedAt": zone.siren_activated_at.isoformat(),
        "activationReason": zone.siren_reason,
    }


@router.post("/sirens/{zone_id}/deactivate")
def deactivate_siren(zone_id: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Siren/zone not found")
    hardware_service.deactivate_siren(zone.id)
    zone.siren_status = False
    zone.siren_reason = "Manually deactivated by operator"
    db.commit()
    return {
        "id": zone.id,
        "name": f"Siren — {zone.name}",
        "currentStatus": "off",
        "zoneStatus": "Safe",
        "village": zone.name,
        "connected": True,
        "lastActivatedAt": zone.siren_activated_at.isoformat() if zone.siren_activated_at else None,
        "activationReason": zone.siren_reason,
    }


@router.get("/map-data")
def get_map_data(db: Session = Depends(get_db)):
    latest_critical = (
        db.query(models.Alert)
        .filter(models.Alert.status == "active")
        .order_by(models.Alert.risk_level.desc(), models.Alert.created_at.desc())
        .first()
    )

    threat = None
    if latest_critical:
        threat = {
            "animal": latest_critical.species or "Unclassified",
            "confidence": f"{latest_critical.confidence:.1%}",
            "currentLocation": latest_critical.camera.name if latest_critical.camera else latest_critical.zone.name,
            "movingToward": latest_critical.zone.name,
            "distance": "Unknown — add a tracking/distance-estimation step",  # TODO
            "riskLevel": latest_critical.risk_level.upper(),
            "siren": f"{latest_critical.zone.name} {'ON' if latest_critical.siren_activated else 'OFF'}",
        }
    else:
        threat = {
            "animal": "None",
            "confidence": "—",
            "currentLocation": "—",
            "movingToward": "—",
            "distance": "—",
            "riskLevel": "LOW",
            "siren": "All clear",
        }

    zones = db.query(models.Zone).all()
    zone_incident_counts = []
    for z in zones:
        count = db.query(models.Alert).filter(models.Alert.zone_id == z.id).count()
        zone_incident_counts.append({"name": z.name, "incidents": count})
    zone_incident_counts.sort(key=lambda x: x["incidents"], reverse=True)

    return {"threat": threat, "zones": zone_incident_counts}


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    alerts = db.query(models.Alert).all()

    species_counts: dict[str, int] = {}
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    direction_counts: dict[str, int] = {}
    false_alarms = 0
    confirmed = 0

    for a in alerts:
        label = a.species or ("Human" if a.event_type == models.EventType.PERSON_DETECTED else "Unclassified")
        species_counts[label] = species_counts.get(label, 0) + 1
        risk_counts[a.risk_level] = risk_counts.get(a.risk_level, 0) + 1
        if a.movement_direction:
            direction_counts[a.movement_direction] = direction_counts.get(a.movement_direction, 0) + 1
        if a.status == "resolved" and a.risk_level == "low":
            false_alarms += 1
        else:
            confirmed += 1

    # Last 6 days, bucketed by day — a simple trend for the analytics charts.
    wildlife_intrusions = []
    human_intrusions = []
    siren_activations = []
    for i in range(5, -1, -1):
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_alerts = [a for a in alerts if day_start <= a.created_at < day_end]
        wildlife_intrusions.append(sum(1 for a in day_alerts if a.event_type == models.EventType.ANIMAL_DETECTED))
        human_intrusions.append(sum(1 for a in day_alerts if a.event_type == models.EventType.PERSON_DETECTED))
        siren_activations.append(sum(1 for a in day_alerts if a.siren_activated))

    return {
        "speciesCounts": [{"label": k, "value": v} for k, v in species_counts.items()],
        "wildlifeIntrusions": wildlife_intrusions,
        "humanIntrusions": human_intrusions,
        "riskLevels": [{"label": k.capitalize(), "value": v} for k, v in risk_counts.items()],
        "movementDirections": [{"label": k, "value": v} for k, v in direction_counts.items()],
        "sirenActivations": siren_activations,
        "falseAlarmStats": {"falseAlarms": false_alarms, "confirmedIntrusions": confirmed},
    }
