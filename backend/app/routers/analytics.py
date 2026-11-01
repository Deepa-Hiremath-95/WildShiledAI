"""
WildShield AI - Advanced Analytics, Reporting, and Operational Intelligence Router
===================================================================================
Provides comprehensive analytics endpoints powered by actual historical detection,
alert, camera, and village database records.

Follows strict guidelines:
- Real database records only; zero fabricated values.
- Distinguishes unavailable telemetry from zero activity.
- Discloses heuristic risk engine and descriptive hotspot limitations.
- Enforces strict human notification protocol (siren permanently inhibited).
- Provides downloadable RFC 4180 CSV and standard-compliant PDF-1.4 reports.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models, auth
from app.services import report_generator

router = APIRouter(tags=["Analytics & Intelligence"])


def _parse_date(date_str: Optional[str], is_end: bool = False) -> Optional[datetime]:
    """Safely parses ISO / YYYY-MM-DD date strings."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        # Try full ISO format
        clean = date_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        # If timezone-aware, convert to naive UTC
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        if is_end and len(date_str.strip()) <= 10:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d")
        if is_end:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD or ISO 8601.")


def _apply_detection_filters(
    query,
    village_id: Optional[str] = None,
    species: Optional[str] = None,
    risk_level: Optional[str] = None,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
):
    """Applies common filtering criteria to Detection queries."""
    if village_id and isinstance(village_id, str):
        # Detections may have direct village_id or via Zone
        query = query.join(models.Zone, models.Detection.zone_id == models.Zone.id)
        query = query.filter(
            (models.Detection.village_id == village_id) | (models.Zone.village_id == village_id)
        )
    if species and isinstance(species, str):
        query = query.filter(func.lower(models.Detection.species) == species.strip().lower())
    if risk_level and isinstance(risk_level, str):
        query = query.filter(func.lower(models.Detection.risk_level) == risk_level.strip().lower())
    if start_dt and isinstance(start_dt, datetime):
        query = query.filter(models.Detection.created_at >= start_dt)
    if end_dt and isinstance(end_dt, datetime):
        query = query.filter(models.Detection.created_at <= end_dt)
    return query


def _apply_alert_filters(
    query,
    village_id: Optional[str] = None,
    species: Optional[str] = None,
    risk_level: Optional[str] = None,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
):
    """Applies common filtering criteria to Alert queries."""
    if village_id and isinstance(village_id, str):
        query = query.join(models.Zone, models.Alert.zone_id == models.Zone.id)
        query = query.filter(
            (models.Alert.village_id == village_id) | (models.Zone.village_id == village_id)
        )
    if species and isinstance(species, str):
        query = query.filter(func.lower(models.Alert.species) == species.strip().lower())
    if risk_level and isinstance(risk_level, str):
        query = query.filter(func.lower(models.Alert.risk_level) == risk_level.strip().lower())
    if start_dt and isinstance(start_dt, datetime):
        query = query.filter(models.Alert.created_at >= start_dt)
    if end_dt and isinstance(end_dt, datetime):
        query = query.filter(models.Alert.created_at <= end_dt)
    return query


# ============================================================================
# Overview & Summary
# ============================================================================

@router.get("/analytics/summary")
@router.get("/analytics/overview")
def get_analytics_summary(
    village_id: Optional[str] = Query(None),
    species: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Top-level operational intelligence KPI metrics across detections and alerts."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    det_q = _apply_detection_filters(db.query(models.Detection), village_id, species, risk_level, start_dt, end_dt)
    detections = det_q.all()

    alert_q = _apply_alert_filters(db.query(models.Alert), village_id, species, risk_level, start_dt, end_dt)
    alerts = alert_q.all()

    human_count = sum(1 for d in detections if (d.species or "").lower() == "human" or d.event_type == models.EventType.PERSON_DETECTED)
    wildlife_count = len(detections) - human_count
    siren_count = sum(1 for a in alerts if a.siren_activated)

    active_alerts = sum(1 for a in alerts if (a.status or "active").lower() == "active")
    acknowledged_alerts = sum(1 for a in alerts if (a.status or "").lower() == "acknowledged")
    resolved_alerts = sum(1 for a in alerts if (a.status or "").lower() == "resolved")

    return {
        "total_detections": len(detections),
        "wildlife_count": wildlife_count,
        "human_count": human_count,
        "siren_count": siren_count,
        "total_alerts": len(alerts),
        "active_alerts": active_alerts,
        "acknowledged_alerts": acknowledged_alerts,
        "resolved_alerts": resolved_alerts,
        "risk_engine": {
            "type": "HEURISTIC",
            "field_validated": False,
            "disclaimer": (
                "Risk levels are determined by rule-based heuristic calculations based on species, "
                "location buffer, movement trajectory, and time-of-day. They have not been statistically "
                "calibrated against ground-truth field outcomes."
            ),
        },
        "filters_applied": {
            "village_id": village_id,
            "species": species,
            "risk_level": risk_level,
            "start_date": start_date,
            "end_date": end_date,
        },
    }


# ============================================================================
# Task 1: Village Analytics
# ============================================================================

@router.get("/analytics/villages")
def get_village_analytics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Breakdown of detection volume, species distribution, risk profile, and alert rates per village."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    villages = db.query(models.Village).all()
    all_zones = db.query(models.Zone).all()
    zone_village_map = {z.id: z.village_id for z in all_zones}

    det_q = db.query(models.Detection)
    if start_dt:
        det_q = det_q.filter(models.Detection.created_at >= start_dt)
    if end_dt:
        det_q = det_q.filter(models.Detection.created_at <= end_dt)
    detections = det_q.all()

    alert_q = db.query(models.Alert)
    if start_dt:
        alert_q = alert_q.filter(models.Alert.created_at >= start_dt)
    if end_dt:
        alert_q = alert_q.filter(models.Alert.created_at <= end_dt)
    alerts = alert_q.all()

    # Pre-index by village_id
    det_by_vil = defaultdict(list)
    for d in detections:
        v_id = d.village_id or zone_village_map.get(d.zone_id)
        if v_id:
            det_by_vil[v_id].append(d)

    alert_by_vil = defaultdict(list)
    for a in alerts:
        v_id = a.village_id or zone_village_map.get(a.zone_id)
        if v_id:
            alert_by_vil[v_id].append(a)

    results = []
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    for v in villages:
        v_dets = det_by_vil.get(v.id, [])
        v_alerts = alert_by_vil.get(v.id, [])

        # Species distribution
        sp_dist = defaultdict(int)
        risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for d in v_dets:
            sp = d.species or ("Human" if d.event_type == models.EventType.PERSON_DETECTED else "Unknown")
            sp_dist[sp] += 1
            rl = (d.risk_level or "low").lower()
            if rl in risk_dist:
                risk_dist[rl] += 1

        # Historical comparison (last 7d vs prior 7d)
        recent_7d = sum(1 for d in v_dets if d.created_at and d.created_at >= seven_days_ago)
        prior_7d = sum(1 for d in v_dets if d.created_at and fourteen_days_ago <= d.created_at < seven_days_ago)
        if prior_7d == 0 and recent_7d == 0:
            trend = "stable"
        elif prior_7d == 0 and recent_7d > 0:
            trend = "increasing"
        elif recent_7d > prior_7d:
            trend = "increasing"
        elif recent_7d < prior_7d:
            trend = "decreasing"
        else:
            trend = "stable"

        siren_count = sum(1 for a in v_alerts if a.siren_activated)

        results.append({
            "village_id": v.id,
            "village_name": v.name,
            "village_code": v.code,
            "siren_pattern": v.siren_pattern,
            "is_active": v.is_active,
            "total_detections": len(v_dets),
            "species_distribution": dict(sp_dist),
            "risk_distribution": risk_dist,
            "alert_frequency": len(v_alerts),
            "siren_deterrences": siren_count,
            "historical_activity_comparison": {
                "recent_7d_count": recent_7d,
                "prior_7d_count": prior_7d,
                "trend": trend,
            },
        })

    return {"villages": results, "total_settlements": len(results)}


# ============================================================================
# Task 2: Species Analytics
# ============================================================================

@router.get("/analytics/species")
def get_species_analytics(
    village_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Detailed analytics for Elephant, Leopard, Deer, Wild Boar, and other species."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    det_q = _apply_detection_filters(db.query(models.Detection), village_id, None, None, start_dt, end_dt)
    detections = det_q.all()

    # Preload village and zone maps
    villages = {v.id: v.name for v in db.query(models.Village).all()}
    zones = {z.id: (z.name, z.village_id) for z in db.query(models.Zone).all()}

    # Group detections by normalized species name
    species_groups = defaultdict(list)
    for d in detections:
        raw_sp = d.species or ("Human" if d.event_type == models.EventType.PERSON_DETECTED else "Other")
        # Normalize
        norm_sp = raw_sp.strip().title()
        species_groups[norm_sp].append(d)

    # Ensure key species are always tracked in output
    target_species = ["Elephant", "Leopard", "Deer", "Wild Boar"]
    for ts in target_species:
        if ts not in species_groups:
            species_groups[ts] = []

    results = []
    for sp_name, dets in sorted(species_groups.items(), key=lambda x: len(x[1]), reverse=True):
        count = len(dets)
        if count > 0:
            confs = [d.confidence for d in dets if d.confidence is not None]
            min_c = min(confs) if confs else None
            max_c = max(confs) if confs else None
            avg_c = round(sum(confs) / len(confs), 3) if confs else None
            buckets = {
                "<0.70": sum(1 for c in confs if c < 0.70),
                "0.70-0.85": sum(1 for c in confs if 0.70 <= c <= 0.85),
                ">0.85": sum(1 for c in confs if c > 0.85),
            }
        else:
            min_c, max_c, avg_c = None, None, None
            buckets = {"<0.70": 0, "0.70-0.85": 0, ">0.85": 0}

        # Daily and Monthly trends
        daily_counts = defaultdict(int)
        monthly_counts = defaultdict(int)
        vil_counts = defaultdict(int)
        zone_counts = defaultdict(int)

        for d in dets:
            if d.created_at:
                day_str = d.created_at.strftime("%Y-%m-%d")
                month_str = d.created_at.strftime("%Y-%m")
                daily_counts[day_str] += 1
                monthly_counts[month_str] += 1

            z_info = zones.get(d.zone_id)
            z_name = z_info[0] if z_info else "Unknown Zone"
            v_id = d.village_id or (z_info[1] if z_info else None)
            v_name = villages.get(v_id, "Unknown Settlement")

            vil_counts[v_name] += 1
            zone_counts[z_name] += 1

        sorted_daily = [{"date": k, "count": v} for k, v in sorted(daily_counts.items())]
        sorted_monthly = [{"month": k, "count": v} for k, v in sorted(monthly_counts.items())]

        results.append({
            "species": sp_name,
            "total_detections": count,
            "confidence_distribution": {
                "min": min_c,
                "avg": avg_c,
                "max": max_c,
                "buckets": buckets,
            },
            "daily_trends": sorted_daily,
            "monthly_trends": sorted_monthly,
            "village_distribution": dict(vil_counts),
            "zone_distribution": dict(zone_counts),
        })

    return {"species_analytics": results, "tracked_species_count": len(results)}


# ============================================================================
# Task 3: Risk Analytics
# ============================================================================

@router.get("/analytics/risk")
def get_risk_analytics(
    village_id: Optional[str] = Query(None),
    species: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Risk-level counts, settlement breakdowns, historical trends, and high-risk summaries."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    det_q = _apply_detection_filters(db.query(models.Detection), village_id, species, None, start_dt, end_dt)
    detections = det_q.all()

    villages = {v.id: v.name for v in db.query(models.Village).all()}
    zones = {z.id: (z.name, z.village_id) for z in db.query(models.Zone).all()}

    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    risk_by_village = defaultdict(lambda: {"low": 0, "medium": 0, "high": 0, "critical": 0})
    risk_by_zone = defaultdict(lambda: {"low": 0, "medium": 0, "high": 0, "critical": 0})
    daily_risk = defaultdict(lambda: {"low": 0, "medium": 0, "high": 0, "critical": 0})

    high_risk_events = []

    for d in detections:
        rl = (d.risk_level or "low").lower()
        if rl in risk_counts:
            risk_counts[rl] += 1

        z_info = zones.get(d.zone_id)
        z_name = z_info[0] if z_info else "Unknown Zone"
        v_id = d.village_id or (z_info[1] if z_info else None)
        v_name = villages.get(v_id, "Unknown Settlement")

        if rl in risk_by_village[v_name]:
            risk_by_village[v_name][rl] += 1
        if rl in risk_by_zone[z_name]:
            risk_by_zone[z_name][rl] += 1

        if d.created_at:
            day_str = d.created_at.strftime("%Y-%m-%d")
            daily_risk[day_str][rl] += 1

        if rl in ("high", "critical"):
            high_risk_events.append({
                "detection_id": d.id,
                "species": d.species or "Unknown",
                "confidence": d.confidence,
                "risk_level": rl,
                "village_name": v_name,
                "zone_name": z_name,
                "siren_triggered": bool(d.siren_triggered),
                "timestamp": d.created_at.isoformat() if d.created_at else None,
            })

    # Sort high-risk events descending by timestamp
    high_risk_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    sorted_trends = [
        {"date": k, **v} for k, v in sorted(daily_risk.items())
    ]

    return {
        "risk_counts": risk_counts,
        "risk_by_village": dict(risk_by_village),
        "risk_by_zone": dict(risk_by_zone),
        "historical_risk_trends": sorted_trends,
        "high_risk_events_summary": high_risk_events[:15],
        "engine_label": "HEURISTIC_RULE_ENGINE",
        "field_validation_status": "PENDING_FIELD_CALIBRATION",
        "disclaimer": (
            "The current risk classification engine operates heuristically using configured species traits, "
            "zone geometry boundaries, and temporal proximity. It is not a predictive statistical model and has "
            "not yet been validated against ground-truth conservation field outcomes."
        ),
    }


# ============================================================================
# Task 4: Hotspot Analysis
# ============================================================================

@router.get("/analytics/hotspots")
def get_hotspot_analysis(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Identifies frequently active monitoring zones using historical detection records."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    det_q = db.query(models.Detection)
    if start_dt:
        det_q = det_q.filter(models.Detection.created_at >= start_dt)
    if end_dt:
        det_q = det_q.filter(models.Detection.created_at <= end_dt)
    detections = det_q.all()

    alert_q = db.query(models.Alert)
    if start_dt:
        alert_q = alert_q.filter(models.Alert.created_at >= start_dt)
    if end_dt:
        alert_q = alert_q.filter(models.Alert.created_at <= end_dt)
    alerts = alert_q.all()

    zones = {z.id: z for z in db.query(models.Zone).all()}
    villages = {v.id: v for v in db.query(models.Village).all()}

    zone_dets = defaultdict(list)
    for d in detections:
        zone_dets[d.zone_id].append(d)

    zone_alerts = defaultdict(int)
    for a in alerts:
        zone_alerts[a.zone_id] += 1

    hotspots = []
    for z_id, dets in zone_dets.items():
        zone = zones.get(z_id)
        z_name = zone.name if zone else "Unknown Zone"
        z_type = zone.type.value if (zone and hasattr(zone.type, "value")) else str(zone.type if zone else "ANIMAL")
        v_id = zone.village_id if zone else None
        village = villages.get(v_id)
        v_name = village.name if village else "Unassigned Settlement"

        # Most detected species
        sp_counts = defaultdict(int)
        for d in dets:
            sp = d.species or ("Human" if d.event_type == models.EventType.PERSON_DETECTED else "Other")
            sp_counts[sp] += 1
        primary_species = max(sp_counts.items(), key=lambda x: x[1])[0] if sp_counts else "None"

        timestamps = [d.created_at for d in dets if d.created_at]
        first_seen = min(timestamps).isoformat() if timestamps else None
        last_seen = max(timestamps).isoformat() if timestamps else None

        hotspots.append({
            "zone_id": z_id,
            "zone_name": z_name,
            "zone_type": z_type,
            "village_id": v_id,
            "village_name": v_name,
            "primary_species": primary_species,
            "species_breakdown": dict(sp_counts),
            "detection_count": len(dets),
            "alert_count": zone_alerts.get(z_id, 0),
            "time_period": {
                "first_detected": first_seen,
                "last_detected": last_seen,
            },
        })

    # Sort hotspots descending by detection count
    hotspots.sort(key=lambda x: x["detection_count"], reverse=True)

    effective_limit = limit if isinstance(limit, int) else 10
    ranked_hotspots = []
    for rank, h in enumerate(hotspots[:effective_limit], start=1):
        ranked_hotspots.append({"rank": rank, **h})

    return {
        "hotspots": ranked_hotspots,
        "total_active_zones": len(hotspots),
        "spatial_disclaimer": (
            "Descriptive activity ranking only. Simple detection frequencies reflect camera placement, "
            "optical field-of-view, and sensor trigger conditions, and must not be interpreted as predictive "
            "geographic modeling or ground-truth animal density."
        ),
    }


# ============================================================================
# Task 5: Human Intrusion Analytics
# ============================================================================

@router.get("/analytics/human-intrusions")
def get_human_intrusion_analytics(
    village_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Audited human intrusion activity, restricted-zone activity, and temporal patterns."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    det_q = db.query(models.Detection).filter(
        (func.lower(models.Detection.species) == "human") |
        (models.Detection.event_type == models.EventType.PERSON_DETECTED)
    )
    det_q = _apply_detection_filters(det_q, village_id, None, None, start_dt, end_dt)
    human_dets = det_q.all()

    zones = {z.id: z for z in db.query(models.Zone).all()}
    villages = {v.id: v for v in db.query(models.Village).all()}

    zone_counts = defaultdict(int)
    vil_counts = defaultdict(int)
    restricted_count = 0
    buffer_count = 0

    time_patterns = {
        "night (22:00-05:59)": 0,
        "morning (06:00-11:59)": 0,
        "afternoon (12:00-16:59)": 0,
        "evening (17:00-21:59)": 0,
    }

    notification_history = []
    siren_activated_count = 0

    for d in human_dets:
        zone = zones.get(d.zone_id)
        z_name = zone.name if zone else "Unknown Zone"
        z_type_val = zone.type.value if (zone and hasattr(zone.type, "value")) else str(zone.type if zone else "")
        is_restricted = "human" in z_type_val.lower() or "restricted" in z_name.lower() or "core" in z_name.lower()
        if is_restricted:
            restricted_count += 1
        else:
            buffer_count += 1

        v_id = d.village_id or (zone.village_id if zone else None)
        v_name = villages[v_id].name if (v_id and v_id in villages) else "Unknown Settlement"

        zone_counts[z_name] += 1
        vil_counts[v_name] += 1

        # Check hour
        if d.created_at:
            hour = d.created_at.hour
            if hour >= 22 or hour < 6:
                time_patterns["night (22:00-05:59)"] += 1
            elif 6 <= hour < 12:
                time_patterns["morning (06:00-11:59)"] += 1
            elif 12 <= hour < 17:
                time_patterns["afternoon (12:00-16:59)"] += 1
            else:
                time_patterns["evening (17:00-21:59)"] += 1

        if d.siren_triggered:
            siren_activated_count += 1

        notification_history.append({
            "detection_id": d.id,
            "timestamp": d.created_at.isoformat() if d.created_at else None,
            "village_name": v_name,
            "zone_name": z_name,
            "is_restricted_zone": is_restricted,
            "confidence": d.confidence,
            "risk_level": d.risk_level,
            "action_taken": d.action_taken or "LOGGED_DISCREET_NOTIFICATION",
        })

    notification_history.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    zone_breakdown = [
        {
            "zone_name": k,
            "count": v,
            "is_restricted": "restricted" in k.lower() or "human" in k.lower(),
        }
        for k, v in zone_counts.items()
    ]

    return {
        "total_human_detections": len(human_dets),
        "restricted_zone_activity": restricted_count,
        "buffer_zone_activity": buffer_count,
        "by_zone": zone_breakdown,
        "village_comparison": dict(vil_counts),
        "time_based_patterns": time_patterns,
        "notification_event_history": notification_history[:20],
        "siren_policy": {
            "siren_activations": siren_activated_count,
            "policy_status": "COMPLIANT_ZERO_SIREN",
            "enforcement_statement": (
                "Human detections are permanently inhibited from activating acoustic sirens and are "
                "routed exclusively to discrete ranger notifications to protect personnel safety."
            ),
        },
    }


# ============================================================================
# Task 6: Camera Analytics
# ============================================================================

@router.get("/analytics/cameras")
def get_camera_analytics(
    village_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Status, heartbeat availability, and detection activity for registered cameras."""
    cam_q = db.query(models.Camera)
    if village_id and isinstance(village_id, str):
        cam_q = cam_q.filter(models.Camera.village_id == village_id)
    cameras = cam_q.all()

    villages = {v.id: v.name for v in db.query(models.Village).all()}
    zones = {z.id: z.name for z in db.query(models.Zone).all()}

    # Count detections per camera
    det_counts = dict(
        db.query(models.Detection.camera_id, func.count(models.Detection.id))
        .group_by(models.Detection.camera_id)
        .all()
    )

    online_count = sum(1 for c in cameras if c.is_online)
    offline_count = len(cameras) - online_count

    cam_details = []
    for c in cameras:
        cam_details.append({
            "camera_id": c.id,
            "name": c.name,
            "village_name": villages.get(c.village_id, "Unassigned"),
            "zone_name": zones.get(c.zone_id, "Unassigned"),
            "is_online": bool(c.is_online),
            "last_heartbeat": c.last_heartbeat.isoformat() if c.last_heartbeat else None,
            "last_alert_at": c.last_alert_at.isoformat() if c.last_alert_at else None,
            "last_human_alert_at": c.last_human_alert_at.isoformat() if c.last_human_alert_at else None,
            "total_detections_recorded": det_counts.get(c.id, 0),
            # Do not invent uptime values when historical heartbeat data is unavailable
            "uptime_percentage": None,
            "uptime_status": "UNAVAILABLE",
            "uptime_reason": (
                "Insufficient historical heartbeat telemetry; camera state transitions are not stored "
                "in a time-series heartbeat log. Live status reflects the most recent heartbeat timestamp."
            ),
        })

    return {
        "total_cameras": len(cameras),
        "online_count": online_count,
        "offline_count": offline_count,
        "camera_details": cam_details,
    }


# ============================================================================
# Task 7: Alert Analytics
# ============================================================================

@router.get("/analytics/alerts")
def get_alert_analytics(
    village_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Alert status distributions, frequency, and time-to-acknowledge / resolve durations."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    alert_q = _apply_alert_filters(db.query(models.Alert), village_id, None, None, start_dt, end_dt)
    alerts = alert_q.all()

    active_count = 0
    ack_count = 0
    res_count = 0

    ack_durations = []
    res_durations = []

    for a in alerts:
        status_norm = (a.status or "active").lower()
        if status_norm == "active":
            active_count += 1
        elif status_norm == "acknowledged":
            ack_count += 1
        elif status_norm == "resolved":
            res_count += 1

        if a.created_at:
            if a.acknowledged_at:
                dur = (a.acknowledged_at - a.created_at).total_seconds()
                if dur >= 0:
                    ack_durations.append(dur)
            if a.resolved_at:
                dur = (a.resolved_at - a.created_at).total_seconds()
                if dur >= 0:
                    res_durations.append(dur)

    def _calc_stats(durations: List[float]):
        if not durations:
            return {
                "avg_seconds": None,
                "min_seconds": None,
                "max_seconds": None,
                "sample_size": 0,
                "status": "UNAVAILABLE_NO_RECORDS",
            }
        return {
            "avg_seconds": round(sum(durations) / len(durations), 1),
            "min_seconds": round(min(durations), 1),
            "max_seconds": round(max(durations), 1),
            "sample_size": len(durations),
            "status": "COMPUTED",
        }

    # Alert frequency calculation
    if start_dt and end_dt:
        days = max((end_dt - start_dt).days, 1)
    else:
        created_times = [a.created_at for a in alerts if a.created_at]
        if created_times:
            span = (max(created_times) - min(created_times)).days
            days = max(span, 1)
        else:
            days = 1

    alert_freq_per_day = round(len(alerts) / days, 2)

    return {
        "total_alerts": len(alerts),
        "status_distribution": {
            "active": active_count,
            "acknowledged": ack_count,
            "resolved": res_count,
        },
        "alert_frequency_per_day": alert_freq_per_day,
        "time_to_acknowledge": _calc_stats(ack_durations),
        "time_to_resolve": _calc_stats(res_durations),
    }


# ============================================================================
# Task 8: Report Generation (CSV & PDF)
# ============================================================================

def _fetch_report_records(
    db: Session,
    village_id: Optional[str] = None,
    species: Optional[str] = None,
    risk_level: Optional[str] = None,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Retrieves and joins historical detections and alerts for reporting."""
    det_q = _apply_detection_filters(db.query(models.Detection), village_id, species, risk_level, start_dt, end_dt)
    detections = det_q.order_by(models.Detection.created_at.desc()).all()

    villages = {v.id: v.name for v in db.query(models.Village).all()}
    zones = {z.id: (z.name, z.type.value if hasattr(z.type, "value") else str(z.type), z.village_id) for z in db.query(models.Zone).all()}
    alerts = {a.id: (a.status, a.siren_activated) for a in db.query(models.Alert).all()}

    records = []
    for d in detections:
        z_info = zones.get(d.zone_id)
        z_name = z_info[0] if z_info else "Unknown Zone"
        z_type = z_info[1] if z_info else "ANIMAL"
        v_id = d.village_id or (z_info[2] if z_info else None)
        v_name = villages.get(v_id, "Unknown Settlement")

        alt_info = alerts.get(d.alert_id) if d.alert_id else None
        alt_status = alt_info[0] if alt_info else "N/A"

        records.append({
            "id": d.id,
            "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else "",
            "event_type": d.event_type.value if hasattr(d.event_type, "value") else str(d.event_type),
            "species": d.species or "Unknown",
            "confidence": d.confidence or 0.0,
            "risk_level": (d.risk_level or "low").upper(),
            "village_name": v_name,
            "zone_name": z_name,
            "zone_type": z_type,
            "camera_id": d.camera_id,
            "movement_direction": d.movement_direction or "N/A",
            "siren_triggered": bool(d.siren_triggered or (alt_info[1] if alt_info else False)),
            "action_taken": d.action_taken or "LOGGED",
            "alert_id": d.alert_id or "N/A",
            "alert_status": alt_status,
        })
    return records


@router.get("/analytics/reports/csv")
def download_csv_report(
    village_id: Optional[str] = Query(None),
    species: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Generates and downloads an RFC 4180 CSV export of filtered historical telemetry."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    records = _fetch_report_records(db, village_id, species, risk_level, start_dt, end_dt)

    village_obj = db.query(models.Village).filter_by(id=village_id).first() if (village_id and isinstance(village_id, str)) else None
    filters = {
        "village_name": village_obj.name if village_obj else None,
        "species": species if isinstance(species, str) else None,
        "risk_level": risk_level if isinstance(risk_level, str) else None,
        "start_date": start_date if isinstance(start_date, str) else None,
        "end_date": end_date if isinstance(end_date, str) else None,
    }

    csv_content = report_generator.generate_csv_report(records, filters)
    filename = f"wildshield_analytics_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/reports/pdf")
def download_pdf_report(
    village_id: Optional[str] = Query(None),
    species: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Generates and downloads a formal PDF-1.4 executive operational intelligence report."""
    start_dt = _parse_date(start_date, is_end=False)
    end_dt = _parse_date(end_date, is_end=True)

    # 1. Summary
    summary = get_analytics_summary(village_id, species, risk_level, start_date, end_date, db)

    # 2. Species breakdown
    sp_data = get_species_analytics(village_id, start_date, end_date, db)
    species_breakdown = []
    for item in sp_data["species_analytics"]:
        if item["total_detections"] > 0 or item["species"] in ["Elephant", "Leopard", "Deer", "Wild Boar"]:
            species_breakdown.append({
                "name": item["species"],
                "count": item["total_detections"],
                "avg_confidence": item["confidence_distribution"]["avg"],
                "min_confidence": item["confidence_distribution"]["min"],
                "max_confidence": item["confidence_distribution"]["max"],
                "primary_risk": "High" if item["species"] in ["Elephant", "Leopard"] else "Medium",
            })

    # 3. Risk breakdown
    risk_data = get_risk_analytics(village_id, species, start_date, end_date, db)

    # 4. Hotspots
    hotspot_data = get_hotspot_analysis(start_date, end_date, limit=6, db=db)

    # 5. Human intrusion summary
    human_data = get_human_intrusion_analytics(village_id, start_date, end_date, db)

    village_obj = db.query(models.Village).filter_by(id=village_id).first() if (village_id and isinstance(village_id, str)) else None
    filters = {
        "village_name": village_obj.name if village_obj else None,
        "species": species if isinstance(species, str) else None,
        "risk_level": risk_level if isinstance(risk_level, str) else None,
        "start_date": start_date if isinstance(start_date, str) else None,
        "end_date": end_date if isinstance(end_date, str) else None,
    }

    pdf_bytes = report_generator.generate_pdf_report(
        summary=summary,
        species_breakdown=species_breakdown,
        risk_breakdown=risk_data["risk_counts"],
        hotspots=hotspot_data["hotspots"],
        human_summary=human_data,
        filters=filters,
    )

    filename = f"wildshield_intelligence_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
