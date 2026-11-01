import asyncio
import base64
import os
import uuid
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models, schemas, alert_engine
from app.auth import get_current_user, get_detection_auth
from app.services.ws_manager import manager

router = APIRouter(tags=["alerts"])

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

_active_siren_tasks: dict[str, asyncio.Task] = {}


async def auto_turn_off_siren(zone_id: str, duration: int, db: Session | None = None):
    """
    Waits for siren_duration_seconds, sets Zone.siren_status = False,
    and broadcasts a 'siren_off' WebSocket event.
    """
    try:
        await asyncio.sleep(duration)
    except asyncio.CancelledError:
        return
    should_close = False
    if db is None:
        from app.main import app
        if get_db in app.dependency_overrides:
            gen = app.dependency_overrides[get_db]()
            db = next(gen)
            should_close = False
        else:
            db = SessionLocal()
            should_close = True

    try:
        zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
        if zone and zone.siren_status:
            zone.siren_status = False
            db.commit()
            await manager.broadcast_siren(zone_id, False, "Playback duration completed")
    finally:
        if should_close:
            db.close()


def schedule_siren_auto_off(zone_id: str, duration: int) -> asyncio.Task:
    """Schedules auto_turn_off_siren in the running event loop as a background task."""
    if zone_id in _active_siren_tasks and not _active_siren_tasks[zone_id].done():
        _active_siren_tasks[zone_id].cancel()
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(auto_turn_off_siren(zone_id, duration))
    except RuntimeError:
        task = asyncio.ensure_future(auto_turn_off_siren(zone_id, duration))
    _active_siren_tasks[zone_id] = task
    return task


def _save_snapshot(base64_data: str) -> str:
    filename = f"{uuid.uuid4()}.jpg"
    path = os.path.join(SNAPSHOT_DIR, filename)
    with open(path, "wb") as f:
        f.write(base64.b64decode(base64_data))
    return f"/snapshots/{filename}"


@router.post("/detections", response_model=schemas.AlertOut | None)
async def ingest_detection(
    event: schemas.DetectionEvent,
    db: Session = Depends(get_db),
    _auth=Depends(get_detection_auth),
):
    """
    Main detection ingestion endpoint called by ai-model webcam loop or edge nodes.
    Feeds alert_engine for rule evaluation, risk assessment, and independent cooldowns.
    Always records detection and broadcasts real-time WebSocket events.
    """
    camera = db.query(models.Camera).filter(models.Camera.id == event.camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    zone = db.query(models.Zone).filter(models.Zone.id == camera.zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone for camera not found")

    snapshot_path = event.snapshot_path
    if event.snapshot_base64 and not snapshot_path:
        snapshot_path = _save_snapshot(event.snapshot_base64)

    result = alert_engine.process_detection(
        db=db,
        camera=camera,
        zone=zone,
        event_type=event.event_type,
        confidence=event.confidence,
        snapshot_path=snapshot_path,
        species=event.species,
        movement_direction=event.movement_direction,
        boundary_crossing=event.boundary_crossing,
    )

    # Broadcast raw detection telemetry to connected dashboards
    if result.detection:
        det_data = {
            "id": result.detection.id,
            "camera_id": camera.id,
            "camera_name": camera.name,
            "zone_id": zone.id,
            "zone_name": zone.name,
            "village_id": camera.village_id or (zone.village_id if zone else None),
            "species": result.detection.species,
            "confidence": result.detection.confidence,
            "risk_level": result.detection.risk_level,
            "action_taken": result.detection.action_taken,
            "siren_triggered": result.detection.siren_triggered,
            "created_at": result.detection.created_at.isoformat(),
        }
        await manager.broadcast_detection(det_data)

    if result.alert:
        if result.alert.siren_activated:
            duration = zone.siren_duration_seconds or 45
            schedule_siren_auto_off(zone.id, duration)
            await manager.broadcast_siren(zone.id, True, result.alert.title or "Animal alert")

        alert_payload = schemas.AlertOut.model_validate(result.alert).model_dump()
        await manager.broadcast_alert(alert_payload)
        return result.alert

    return None


@router.get("/alerts", response_model=list[schemas.AlertOut])
def list_alerts(
    zone_id: Optional[str] = None,
    village_id: Optional[str] = None,
    species: Optional[str] = None,
    status: Optional[str] = None,
    read: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Returns alerts history with optional multi-criteria filtering and pagination."""
    q = db.query(models.Alert).order_by(models.Alert.created_at.desc())
    if zone_id:
        q = q.filter(models.Alert.zone_id == zone_id)
    if village_id:
        q = q.filter(models.Alert.village_id == village_id)
    if species:
        q = q.filter(models.Alert.species.ilike(f"%{species}%"))
    if status:
        q = q.filter(models.Alert.status == status)
    if read is not None:
        q = q.filter(models.Alert.read == read)
    return q.offset(skip).limit(limit).all()


@router.get("/alerts/{alert_id}", response_model=schemas.AlertOut)
def get_alert_detail(alert_id: str, db: Session = Depends(get_db)):
    """Returns details of a specific alert."""
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=schemas.AlertOut)
@router.patch("/alerts/{alert_id}/resolve", response_model=schemas.AlertOut)
async def resolve_alert(
    alert_id: str,
    resolve_in: Optional[schemas.AlertResolveUpdate] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Marks an alert as resolved and records an audit log entry."""
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.utcnow()
    alert.status = "resolved"
    alert.resolved_at = now
    alert.resolved_by = current_user.username
    alert.updated_at = now

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="ALERT_RESOLVED",
        resource_type="alert",
        resource_id=alert.id,
        details=json.dumps({"notes": resolve_in.notes if resolve_in else None, "title": alert.title}),
        created_at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(alert)

    await manager.broadcast_alert_status(alert.id, "resolved", bool(alert.read))
    return alert


@router.patch("/alerts/{alert_id}/read")
@router.post("/alerts/{alert_id}/read")
async def toggle_alert_read(
    alert_id: str,
    read_in: Optional[schemas.AlertReadUpdate] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Acknowledges or toggles read state of an alert."""
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.utcnow()
    if read_in and read_in.read is not None:
        alert.read = read_in.read
    else:
        alert.read = not bool(alert.read)

    if alert.read:
        alert.acknowledged_at = now
        alert.acknowledged_by = current_user.username

    alert.updated_at = now

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="ALERT_ACKNOWLEDGED" if alert.read else "ALERT_UNREAD",
        resource_type="alert",
        resource_id=alert.id,
        details=json.dumps({"read": alert.read, "title": alert.title}),
        created_at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(alert)

    await manager.broadcast_alert_status(alert.id, alert.status, bool(alert.read))
    return {
        "id": alert.id,
        "read": alert.read,
        "status": alert.status,
        "acknowledged_by": alert.acknowledged_by,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
    }


# Operational alias for acknowledge_alert
acknowledge_alert = toggle_alert_read


@router.post("/alerts/mark-all-read")
async def mark_all_alerts_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Bulk acknowledges all unread alerts."""
    now = datetime.utcnow()
    count = db.query(models.Alert).filter(models.Alert.read == False).update(
        {"read": True, "acknowledged_at": now, "acknowledged_by": current_user.username, "updated_at": now}
    )
    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="ALL_ALERTS_ACKNOWLEDGED",
        resource_type="alert",
        resource_id=None,
        details=json.dumps({"count": count}),
        created_at=now,
    )
    db.add(audit)
    db.commit()

    await manager.broadcast("all_alerts_acknowledged", {"count": count, "operator": current_user.username})
    return {"updated": count, "status": "ok"}
