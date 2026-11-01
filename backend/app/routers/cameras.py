import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import require_admin, get_current_user
from app.services.ws_manager import manager

router = APIRouter(prefix="/cameras", tags=["cameras"])

import re


def _sanitize_stream_source(source: Optional[str]) -> Optional[str]:
    """Masks embedded credentials in RTSP/HTTP stream URLs (e.g. rtsp://user:pass@host)."""
    if not source:
        return source
    return re.sub(r'(://[^:]+:)([^@]+)(@)', r'\1***\3', source)

CAMERA_OFFLINE_THRESHOLD_SECONDS = 90


def compute_camera_online(camera: models.Camera) -> bool:
    """Returns True only if a heartbeat was received within the last 90 seconds."""
    if camera.last_heartbeat is None:
        return False
    return datetime.utcnow() - camera.last_heartbeat < timedelta(seconds=CAMERA_OFFLINE_THRESHOLD_SECONDS)


def _enrich_camera(cam: models.Camera) -> schemas.CameraOut:
    is_online = compute_camera_online(cam)
    vil_name = cam.village.name if cam.village else (cam.zone.village.name if (cam.zone and cam.zone.village) else None)
    zone_name = cam.zone.name if cam.zone else None

    return schemas.CameraOut(
        id=cam.id,
        zone_id=cam.zone_id,
        village_id=cam.village_id,
        name=cam.name,
        stream_source=_sanitize_stream_source(cam.stream_source),
        is_online=is_online,
        last_heartbeat=cam.last_heartbeat,
        last_alert_at=cam.last_alert_at,
        last_human_alert_at=cam.last_human_alert_at,
        created_at=cam.created_at,
        village=vil_name,
        zone=zone_name,
    )


@router.post("", response_model=schemas.CameraOut)
async def create_camera(
    camera_in: schemas.CameraCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Registers a new camera node and associates it with a monitoring zone and village."""
    zone = db.query(models.Zone).filter(models.Zone.id == camera_in.zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    stream_src = camera_in.stream_source or camera_in.stream_url or "OpenCV Device #0"
    village_id = camera_in.village_id or zone.village_id

    camera = models.Camera(
        name=camera_in.name,
        zone_id=camera_in.zone_id,
        village_id=village_id,
        stream_source=stream_src,
        is_online=True,
        last_heartbeat=datetime.utcnow(),
    )
    db.add(camera)
    db.flush()

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="CAMERA_REGISTERED",
        resource_type="camera",
        resource_id=camera.id,
        details=json.dumps({"name": camera.name, "zone_id": camera.zone_id}),
    )
    db.add(audit)
    db.commit()
    db.refresh(camera)

    await manager.broadcast_camera_status(camera.id, True)
    return _enrich_camera(camera)


@router.get("", response_model=list[schemas.CameraOut])
def list_cameras(
    zone_id: Optional[str] = None,
    village_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Returns camera nodes list with read-time heartbeat online status."""
    q = db.query(models.Camera)
    if zone_id:
        q = q.filter(models.Camera.zone_id == zone_id)
    if village_id:
        q = q.filter(models.Camera.village_id == village_id)

    cameras = q.all()
    return [_enrich_camera(c) for c in cameras]


@router.get("/{camera_id}", response_model=schemas.CameraOut)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    """Returns details of a specific camera node."""
    camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return _enrich_camera(camera)


@router.patch("/{camera_id}", response_model=schemas.CameraOut)
@router.put("/{camera_id}", response_model=schemas.CameraOut)
async def update_camera(
    camera_id: str,
    camera_in: schemas.CameraUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Updates camera configuration (name, zone, stream source)."""
    camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    data = camera_in.model_dump(exclude_unset=True)
    if "stream_url" in data and not data.get("stream_source"):
        data["stream_source"] = data.pop("stream_url")

    for field, val in data.items():
        setattr(camera, field, val)

    camera.updated_at = datetime.utcnow()
    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="CAMERA_UPDATED",
        resource_type="camera",
        resource_id=camera.id,
        details=json.dumps(data),
    )
    db.add(audit)
    db.commit()
    db.refresh(camera)

    return _enrich_camera(camera)


@router.delete("/{camera_id}")
async def delete_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Removes a camera node from the registry."""
    camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Safety check: Prevent accidental destruction of historical records
    has_alerts = db.query(models.Alert).filter(models.Alert.camera_id == camera_id).first() is not None
    has_dets = db.query(models.Detection).filter(models.Detection.camera_id == camera_id).first() is not None
    if has_alerts or has_dets:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete camera with historical detection or alert records. Deactivate or reassign the camera instead.",
        )

    db.delete(camera)
    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="CAMERA_DELETED",
        resource_type="camera",
        resource_id=camera_id,
    )
    db.add(audit)
    db.commit()

    await manager.broadcast_camera_status(camera_id, False)
    return {"deleted": camera_id}


@router.post("/{camera_id}/heartbeat", response_model=schemas.CameraOut)
async def heartbeat(
    camera_id: str,
    hb: Optional[schemas.CameraHeartbeat] = None,
    db: Session = Depends(get_db),
):
    """
    Called periodically by ai-model or edge camera loop to report operational health.
    Updates last_heartbeat timestamp and broadcasts status change to dashboards.
    """
    camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    is_online = hb.is_online if hb else True
    camera.is_online = is_online
    camera.last_heartbeat = datetime.utcnow()
    db.commit()
    db.refresh(camera)

    await manager.broadcast_camera_status(camera.id, is_online)
    return _enrich_camera(camera)
