import json
from datetime import datetime
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import require_admin, get_current_user
from app.services.ws_manager import manager

router = APIRouter(tags=["settings"])


DEFAULT_SETTINGS = {
    "min_confidence": 0.60,
    "animal_siren_cooldown_seconds": 90,
    "human_notification_cooldown_seconds": 10,
    "duplicate_detection_window_seconds": 10,
    "siren_duration_seconds": 45,
    "excluded_species": ["peacock"],
    "monitoring_preferences": {
        "audio_alerts": True,
        "auto_resolve_after_hours": 24,
        "human_intrusion_priority": "high",
        "enforce_village_camera_binding": True
    }
}


@router.get("/settings", response_model=schemas.SystemSettingsOut)
def get_system_settings(db: Session = Depends(get_db)):
    """Returns persistent global system settings with fallback defaults."""
    res = dict(DEFAULT_SETTINGS)
    latest_update = None

    rows = db.query(models.SystemSetting).all()
    for row in rows:
        key = row.key
        try:
            val = json.loads(row.value)
        except Exception:
            val = row.value

        if key in ("min_confidence",):
            res[key] = float(val)
        elif key in ("animal_siren_cooldown_seconds", "human_notification_cooldown_seconds", "duplicate_detection_window_seconds", "siren_duration_seconds"):
            res[key] = int(val)
        elif key == "excluded_species":
            res[key] = list(val) if isinstance(val, list) else [val]
        elif key == "monitoring_preferences":
            res[key] = dict(val) if isinstance(val, dict) else {}
        else:
            res[key] = val

        if row.updated_at and (latest_update is None or row.updated_at > latest_update):
            latest_update = row.updated_at

    res["updated_at"] = latest_update
    return schemas.SystemSettingsOut(**res)


@router.patch("/settings", response_model=schemas.SystemSettingsOut)
async def update_system_settings(
    settings_in: schemas.SystemSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Updates global system settings (confidence thresholds, animal cooldowns, excluded species).
    Persists changes to the database and logs an audit trail.
    """
    data = settings_in.model_dump(exclude_unset=True)
    if not data:
        return get_system_settings(db)

    now = datetime.utcnow()
    for key, value in data.items():
        if value is None:
            continue
        row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
        serialized = json.dumps(value) if isinstance(value, (list, dict, bool)) else str(value)
        if row:
            row.value = serialized
            row.updated_at = now
        else:
            row = models.SystemSetting(key=key, value=serialized, updated_at=now)
            db.add(row)

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="SETTINGS_UPDATED",
        resource_type="settings",
        details=json.dumps(data, default=str),
        created_at=now,
    )
    db.add(audit)
    db.commit()

    updated = get_system_settings(db)
    await manager.broadcast_settings_updated(updated.model_dump(mode="json"))
    return updated


@router.get("/audit-logs", response_model=list[schemas.AuditLogOut])
def list_audit_logs(
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Returns chronological audit logs of operator actions, status changes, and settings updates."""
    q = db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc())
    if resource_type:
        q = q.filter(models.AuditLog.resource_type == resource_type)
    if action:
        q = q.filter(models.AuditLog.action == action)
    return q.offset(skip).limit(limit).all()


@router.get("/detections/history", response_model=list[schemas.DetectionOut])
def get_detections_history(
    species: Optional[str] = None,
    camera_id: Optional[str] = None,
    village_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Returns historical detection event logs from the database."""
    q = db.query(models.Detection).order_by(models.Detection.created_at.desc())
    if species:
        q = q.filter(models.Detection.species.ilike(f"%{species}%"))
    if camera_id:
        q = q.filter(models.Detection.camera_id == camera_id)
    if village_id:
        q = q.filter(models.Detection.village_id == village_id)

    dets = q.offset(skip).limit(limit).all()

    out = []
    for d in dets:
        loc = d.camera.name if d.camera else d.camera_id
        vil_name = d.village.name if d.village else (d.zone.name if d.zone else "Village Sector")
        out.append(
            schemas.DetectionOut(
                id=d.id,
                camera_id=d.camera_id,
                zone_id=d.zone_id,
                village_id=d.village_id,
                event_type=d.event_type,
                species=d.species,
                confidence=d.confidence,
                movement_direction=d.movement_direction,
                boundary_crossing=bool(d.boundary_crossing),
                risk_level=d.risk_level or "low",
                action_taken=d.action_taken,
                siren_triggered=bool(d.siren_triggered),
                snapshot_path=d.snapshot_path,
                alert_id=d.alert_id,
                created_at=d.created_at,
                location=loc,
                affectedVillage=vil_name,
                type="human" if d.event_type == models.EventType.PERSON_DETECTED else "animal",
                timestamp=d.created_at.isoformat(),
                sirenStatus="on" if d.siren_triggered else "off",
                classification=d.species,
                imageLabel="Detection image" if d.snapshot_path else "No image captured",
                snapshotUrl=d.snapshot_path,
            )
        )
    return out
