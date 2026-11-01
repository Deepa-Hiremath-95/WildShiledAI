import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import require_admin, get_current_user
from app.services.ws_manager import manager

router = APIRouter(prefix="/villages", tags=["villages"])


def _compute_village_status(v: models.Village, db: Session) -> tuple[str, str]:
    """
    Computes village status ('at-risk' | 'safe') and sirenStatus ('on' | 'off')
    based on linked zones, active critical alerts in the last 2 hours, and active sirens.
    """
    zone_ids = [z.id for z in v.zones] if v.zones else []

    # Check if any linked zone has siren on
    siren_on = any(z.siren_status for z in v.zones) if v.zones else False

    # Check for recent critical alerts
    recent_critical = False
    if zone_ids:
        crit_alert = (
            db.query(models.Alert)
            .filter(
                models.Alert.zone_id.in_(zone_ids),
                models.Alert.status == "active",
                models.Alert.risk_level.in_(["high", "critical"]),
                models.Alert.created_at >= datetime.utcnow() - timedelta(hours=2),
            )
            .first()
        )
        recent_critical = bool(crit_alert)

    status = "at-risk" if (siren_on or recent_critical) else "safe"
    siren_status = "on" if siren_on else "off"
    return status, siren_status


def _enrich_village(v: models.Village, db: Session) -> dict:
    status, siren_status = _compute_village_status(v, db)
    primary_zone = v.zones[0].name if v.zones else (v.name or "Zone A")
    siren_id = v.zones[0].id if v.zones else v.id

    return {
        "id": v.id,
        "name": v.name,
        "code": v.code or f"VIL-{v.id[:6].upper()}",
        "description": v.description,
        "siren_pattern": v.siren_pattern or "pattern_1",
        "emergency_contact": v.emergency_contact or "Forest Range Office",
        "latitude": v.latitude,
        "longitude": v.longitude,
        "lat": v.latitude,
        "lng": v.longitude,
        "zone": primary_zone,
        "status": status,
        "sirenId": siren_id,
        "sirenStatus": siren_status,
        "cameras_count": len(v.cameras) if v.cameras else 0,
        "zones_count": len(v.zones) if v.zones else 0,
        "is_active": v.is_active,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


@router.get("")
def list_villages(db: Session = Depends(get_db)):
    """
    Returns list of all registered villages. Matches frontend expectations
    for village management, overview KPIs, and map cards.
    """
    villages = db.query(models.Village).filter(models.Village.is_active == True).all()

    # If villages table has rows, enrich and return
    if villages:
        return [_enrich_village(v, db) for v in villages]

    # Fallback to zones if villages haven't been seeded yet
    zones = db.query(models.Zone).all()
    out = []
    for z in zones:
        out.append({
            "id": z.id,
            "name": z.name,
            "code": f"VIL-{z.id[:6].upper()}",
            "zone": z.name,
            "status": "at-risk" if z.siren_status else "safe",
            "sirenId": z.id,
            "sirenStatus": "on" if z.siren_status else "off",
            "lat": z.latitude,
            "lng": z.longitude,
            "latitude": z.latitude,
            "longitude": z.longitude,
            "siren_pattern": "pattern_1",
            "emergency_contact": "Range Dispatch (+91-9876543210)",
            "cameras_count": len(z.cameras) if z.cameras else 0,
            "zones_count": 1,
            "is_active": True,
        })
    return out


@router.post("")
async def create_village(
    village_in: schemas.VillageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Registers a new village with name, code, emergency contact, and siren sound configuration."""
    existing = db.query(models.Village).filter(models.Village.name == village_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Village with this name already exists")
    if village_in.code:
        existing_code = db.query(models.Village).filter(models.Village.code == village_in.code).first()
        if existing_code:
            raise HTTPException(status_code=400, detail="Village with this code already exists")

    village = models.Village(
        name=village_in.name,
        code=village_in.code,
        description=village_in.description,
        siren_pattern=village_in.siren_pattern or "pattern_1",
        emergency_contact=village_in.emergency_contact,
        latitude=village_in.latitude,
        longitude=village_in.longitude,
        is_active=village_in.is_active,
    )
    db.add(village)
    db.flush()

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="VILLAGE_REGISTERED",
        resource_type="village",
        resource_id=village.id,
        details=json.dumps({"name": village.name, "siren_pattern": village.siren_pattern}),
    )
    db.add(audit)
    db.commit()
    db.refresh(village)

    await manager.broadcast("village_registered", {"id": village.id, "name": village.name})
    return _enrich_village(village, db)


@router.get("/{village_id}")
def get_village(village_id: str, db: Session = Depends(get_db)):
    """Returns details of a single village."""
    village = db.query(models.Village).filter(models.Village.id == village_id).first()
    if not village:
        # Check zone id fallback
        zone = db.query(models.Zone).filter(models.Zone.id == village_id).first()
        if zone:
            return {
                "id": zone.id,
                "name": zone.name,
                "zone": zone.name,
                "status": "at-risk" if zone.siren_status else "safe",
                "lat": zone.latitude,
                "lng": zone.longitude,
            }
        raise HTTPException(status_code=404, detail="Village not found")
    return _enrich_village(village, db)


@router.patch("/{village_id}")
@router.put("/{village_id}")
async def update_village(
    village_id: str,
    village_in: schemas.VillageUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Updates village configuration, siren sound profile, or emergency contacts."""
    village = db.query(models.Village).filter(models.Village.id == village_id).first()
    if not village:
        raise HTTPException(status_code=404, detail="Village not found")

    data = village_in.model_dump(exclude_unset=True)
    for field, val in data.items():
        setattr(village, field, val)

    village.updated_at = datetime.utcnow()
    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="VILLAGE_UPDATED",
        resource_type="village",
        resource_id=village.id,
        details=json.dumps(data),
    )
    db.add(audit)
    db.commit()
    db.refresh(village)

    await manager.broadcast("village_updated", {"id": village.id, "name": village.name})
    return _enrich_village(village, db)


@router.delete("/{village_id}")
async def delete_village(
    village_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Soft-deactivates a village."""
    village = db.query(models.Village).filter(models.Village.id == village_id).first()
    if not village:
        raise HTTPException(status_code=404, detail="Village not found")

    village.is_active = False
    village.updated_at = datetime.utcnow()

    audit = models.AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="VILLAGE_DEACTIVATED",
        resource_type="village",
        resource_id=village.id,
    )
    db.add(audit)
    db.commit()

    await manager.broadcast("village_deactivated", {"id": village.id})
    return {"status": "deactivated", "id": village_id}
