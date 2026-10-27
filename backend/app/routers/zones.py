from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import require_admin, get_current_user

router = APIRouter(prefix="/zones", tags=["zones"])


@router.post("", response_model=schemas.ZoneOut)
def create_zone(zone_in: schemas.ZoneCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    zone = models.Zone(**zone_in.model_dump())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


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
    village_name = z.name.split("—")[0].strip() if "—" in z.name else z.name

    return schemas.ZoneOut(
        id=z.id,
        name=z.name,
        type=z.type,
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
    )


@router.get("", response_model=list[schemas.ZoneOut])
def list_zones(db: Session = Depends(get_db)):
    zones = db.query(models.Zone).all()
    return [_enrich_zone(z, db) for z in zones]


@router.get("/{zone_id}", response_model=schemas.ZoneOut)
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return _enrich_zone(zone, db)


@router.patch("/{zone_id}", response_model=schemas.ZoneOut)
def update_zone(
    zone_id: str, zone_in: schemas.ZoneCreate, db: Session = Depends(get_db), _=Depends(require_admin)
):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    for field, value in zone_in.model_dump().items():
        setattr(zone, field, value)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}")
def delete_zone(zone_id: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    zone = db.query(models.Zone).filter(models.Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(zone)
    db.commit()
    return {"deleted": zone_id}
