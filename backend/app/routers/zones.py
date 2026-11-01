import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import require_admin, get_current_user
from app.services.ws_manager import manager

router = APIRouter(prefix="/zones", tags=["zones"])


def _enrich_zone(z: models.Zone, db: Session) -> schemas.ZoneOut:
    recent_crit = (
        db.query(models.Alert)
        .filter(
            models.Alert.zone_id == z.id,
            models.Alert.status == "active",
            models.Alert.risk_level.in_(["high", "critical"]),
        )
        .first()
    )
    incidents_count = db.query(models.Alert).filter(models.Alert.zone_id == z.id).count()
    village_name = z.village.name if z.village else (z.name.split("—")[0].strip() if "—" in z.name else z.name)

    return schemas.ZoneOut(
        id=z.id,
        name=z.name,
        type=z.type,
        village_id=z.village_id,
        latitude=z.latitude,
        longitude=z.longitude,
        lat=z.latitude,
        lng=z.longitude,
        status="at-risk" if (recent_crit or z.siren_status) else "safe",
        village=village_name,
        incidents=incidents_count,
        confidence_threshold=z.confidence_threshold,
        cooldown_seconds=z.cooldown_seconds,
        siren_duration_seconds=z.siren_duration_seconds,
        created_at=z.created_at,
        updated_at=z.updated_at,
    )


@router.post("", response_model=schemas.ZoneOut)
async def create_zone(
    zone_in: schemas.ZoneCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Registers a new monitoring zone and associates it with a village."""
    if zone_in.village_id:
        vil = db.query(models.Village).filter(models.Village.id == zone_in.village_id).first()
        if not vil:
            raise HTTPException(status_code=404, detail="Village not found")

    zone = models.Zone(**zone_in.model_dump())
    db.add(zone)
    db.flush()

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="ZONE_REGISTERED",
        resource_type="zone",
        resource_id=zone.id,
        details=json.dumps({"name": zone.name, "type": zone.type.value}),
    )
    db.add(audit)
    db.commit()
    db.refresh(zone)

    await manager.broadcast("zone_registered", {"id": zone.id, "name": zone.name})
    return _enrich_zone(zone, db)


@router.get("", response_model=list[schemas.ZoneOut])
def list_zones(village_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Returns all monitoring zones."""
    q = db.query(models.Zone)
    if village_id:
        q = q.filter(models.Zone.village_id == village_id)
    zones = q.all()
    return [_enrich_zone(z, db) for z in zones]


@router.get("/{zone_id}", response_model=schemas.ZoneOut)
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    """Returns details of a specific monitoring zone."""
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return _enrich_zone(zone, db)


@router.patch("/{zone_id}", response_model=schemas.ZoneOut)
@router.put("/{zone_id}", response_model=schemas.ZoneOut)
async def update_zone(
    zone_id: str,
    zone_in: schemas.ZoneUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Updates zone thresholds, cooldowns, or village association."""
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    data = zone_in.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(zone, field, value)

    zone.updated_at = datetime.utcnow()
    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="ZONE_UPDATED",
        resource_type="zone",
        resource_id=zone.id,
        details=json.dumps(data, default=str),
    )
    db.add(audit)
    db.commit()
    db.refresh(zone)

    await manager.broadcast("zone_updated", {"id": zone.id, "name": zone.name})
    return _enrich_zone(zone, db)


@router.delete("/{zone_id}")
async def delete_zone(
    zone_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Deletes a monitoring zone."""
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Safety check: Prevent accidental destruction of historical records
    has_alerts = db.query(models.Alert).filter(models.Alert.zone_id == zone_id).first() is not None
    has_dets = db.query(models.Detection).filter(models.Detection.zone_id == zone_id).first() is not None
    if has_alerts or has_dets:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete zone with historical detection or alert records. Deactivate or archive the zone instead.",
        )

    db.delete(zone)
    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="ZONE_DELETED",
        resource_type="zone",
        resource_id=zone_id,
    )
    db.add(audit)
    db.commit()

    await manager.broadcast("zone_deleted", {"id": zone_id})
    return {"deleted": zone_id}
