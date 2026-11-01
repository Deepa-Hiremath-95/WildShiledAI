"""
Populates the database with zones, cameras, contacts, an admin user, and realistic
intrusion alerts/detections so the dashboard is fully functional and data-driven
immediately, mirroring the shape of the mock data in frontend/api-service.js
(Village 1/2/3, Zone A/B/C) with zero hardcoded numbers.

Run once after the tables exist:
    python -m app.seed
"""
import sys
from datetime import datetime, timedelta

from app.database import SessionLocal, Base, engine
from app import models, auth

Base.metadata.create_all(bind=engine)


def run(reset: bool = False):
    db = SessionLocal()
    try:
        if reset:
            print("Resetting database tables...")
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)

        # Check if already seeded
        existing_zone = db.query(models.Zone).first()
        if existing_zone and db.query(models.Alert).first():
            print("Database already has data and alerts — skipping seed.")
            return

        now = datetime.utcnow()

        # 1. Zones
        village1 = db.query(models.Zone).filter(models.Zone.name.like("%Village 1%")).first()
        if not village1:
            village1 = models.Zone(
                name="Village 1 — Zone A",
                type=models.ZoneType.ANIMAL,
                latitude=11.685,
                longitude=76.620,
                confidence_threshold=0.6,
                cooldown_seconds=90,
                siren_duration_seconds=45,
                siren_status=True,
                siren_activated_at=now - timedelta(minutes=18),
                siren_reason="Lion moving toward Village 1",
            )
            db.add(village1)

        village2 = db.query(models.Zone).filter(models.Zone.name.like("%Village 2%")).first()
        if not village2:
            village2 = models.Zone(
                name="Village 2 — Zone B",
                type=models.ZoneType.ANIMAL,
                latitude=11.692,
                longitude=76.635,
                confidence_threshold=0.6,
                cooldown_seconds=90,
                siren_duration_seconds=45,
                siren_status=False,
                siren_reason="No active threat",
            )
            db.add(village2)

        restricted = db.query(models.Zone).filter(models.Zone.name.like("%Core Reserve%")).first()
        if not restricted:
            restricted = models.Zone(
                name="Core Reserve — Zone C",
                type=models.ZoneType.RESTRICTED,
                latitude=11.678,
                longitude=76.610,
                confidence_threshold=0.65,
                cooldown_seconds=120,
                siren_duration_seconds=45,
                siren_status=False,
                siren_reason="Discreet patrol monitoring",
            )
            db.add(restricted)

        db.flush()

        # 2. Cameras
        cam1 = db.query(models.Camera).filter(models.Camera.zone_id == village1.id).first()
        if not cam1:
            cam1 = models.Camera(
                zone_id=village1.id,
                name="North Ridge Trail Cam",
                stream_source="0",
                is_online=True,
                last_heartbeat=now,
            )
            db.add(cam1)

        cam2 = db.query(models.Camera).filter(models.Camera.zone_id == village2.id).first()
        if not cam2:
            cam2 = models.Camera(
                zone_id=village2.id,
                name="Riverline Trail Cam",
                stream_source="1",
                is_online=True,
                last_heartbeat=now,
            )
            db.add(cam2)

        cam3 = db.query(models.Camera).filter(models.Camera.zone_id == restricted.id).first()
        if not cam3:
            cam3 = models.Camera(
                zone_id=restricted.id,
                name="East Ridge Access Cam",
                stream_source="2",
                is_online=True,
                last_heartbeat=now,
            )
            db.add(cam3)

        # Ensure Phase 2/3 test cameras (CAM-001, CAM-002, CAM-003) exist for live webcam & pipeline testing
        for cid, zid, cname, src in [
            ("CAM-001", village1.id, "Laptop Webcam (Village A Test)", "0"),
            ("CAM-002", village2.id, "Village B Perimeter Camera", "1"),
            ("CAM-003", restricted.id, "Core Reserve Access Cam", "2"),
        ]:
            if not db.query(models.Camera).filter(models.Camera.id == cid).first():
                db.add(models.Camera(id=cid, zone_id=zid, name=cname, stream_source=src, is_online=True, last_heartbeat=now))

        db.flush()

        # 3. Contacts
        forest_officer = db.query(models.Contact).filter(models.Contact.phone_number == "+910000000001").first()
        if not forest_officer:
            forest_officer = models.Contact(name="Forest Officer Desk", phone_number="+910000000001", role="authority")
            db.add(forest_officer)

        ranger = db.query(models.Contact).filter(models.Contact.phone_number == "+910000000002").first()
        if not ranger:
            ranger = models.Contact(name="Ranger Patrol Unit", phone_number="+910000000002", role="authority")
            db.add(ranger)

        db.flush()

        # Link Zone Contacts
        if not db.query(models.ZoneContact).first():
            db.add_all([
                models.ZoneContact(zone_id=village1.id, contact_id=forest_officer.id),
                models.ZoneContact(zone_id=village2.id, contact_id=forest_officer.id),
                models.ZoneContact(zone_id=restricted.id, contact_id=ranger.id),
            ])

        # 4. Admin User
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            admin = models.User(
                username="admin",
                hashed_password=auth.hash_password("changeme123"),
                role=models.UserRole.ADMIN,
                full_name="Forest Officer",
                email="officer@wildshield.ai",
                location="Central Forest Command",
                two_factor_enabled=True,
                last_login_at=now - timedelta(minutes=10),
            )
            db.add(admin)
        else:
            admin.full_name = "Forest Officer"
            admin.email = "officer@wildshield.ai"
            admin.location = "Central Forest Command"
            admin.two_factor_enabled = True
            admin.last_login_at = now - timedelta(minutes=10)

        # 5. Seed Alerts / Detections if none exist
        if db.query(models.Alert).count() == 0:
            sample_alerts = [
                # Critical active alert: Lion near Village 1
                models.Alert(
                    zone_id=village1.id,
                    camera_id=cam1.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.963,
                    species="Lion",
                    movement_direction="South-East",
                    boundary_crossing=True,
                    risk_level="critical",
                    status="active",
                    siren_activated=True,
                    sms_sent=True,
                    read=False,
                    title="Lion movement near boundary",
                    created_at=now - timedelta(minutes=18),
                ),
                # High risk active alert: Elephant near Village 2
                models.Alert(
                    zone_id=village2.id,
                    camera_id=cam2.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.912,
                    species="Elephant",
                    movement_direction="North",
                    boundary_crossing=False,
                    risk_level="high",
                    status="active",
                    siren_activated=False,
                    sms_sent=True,
                    read=False,
                    title="Elephant intrusion detected",
                    created_at=now - timedelta(hours=1, minutes=45),
                ),
                # Human activity alert in Core Reserve (resolved)
                models.Alert(
                    zone_id=restricted.id,
                    camera_id=cam3.id,
                    event_type=models.EventType.PERSON_DETECTED,
                    confidence=0.948,
                    species="Human",
                    movement_direction="Northwest",
                    boundary_crossing=True,
                    risk_level="critical",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=True,
                    read=True,
                    title="Human intrusion near core boundary line",
                    created_at=now - timedelta(hours=5),
                ),
                # Human sensor detection (resolved, low risk false alarm)
                models.Alert(
                    zone_id=restricted.id,
                    camera_id=cam3.id,
                    event_type=models.EventType.PERSON_DETECTED,
                    confidence=0.885,
                    species="Human",
                    movement_direction="West",
                    boundary_crossing=False,
                    risk_level="low",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=False,
                    read=True,
                    title="Human activity near sensor line (Ranger patrol)",
                    created_at=now - timedelta(hours=11),
                ),
                # Animal detection: Wild Boar near Village 2
                models.Alert(
                    zone_id=village2.id,
                    camera_id=cam2.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.745,
                    species="Wild Boar",
                    movement_direction="South",
                    boundary_crossing=False,
                    risk_level="low",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=False,
                    read=True,
                    title="Wild Boar in crop border",
                    created_at=now - timedelta(hours=19),
                ),
                # Historical alerts across previous 5 days for analytics charts
                models.Alert(
                    zone_id=village1.id,
                    camera_id=cam1.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.92,
                    species="Leopard",
                    movement_direction="South-East",
                    boundary_crossing=True,
                    risk_level="high",
                    status="resolved",
                    siren_activated=True,
                    sms_sent=True,
                    read=True,
                    title="Leopard detected near perimeter",
                    created_at=now - timedelta(days=1, hours=2),
                ),
                models.Alert(
                    zone_id=village2.id,
                    camera_id=cam2.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.89,
                    species="Elephant",
                    movement_direction="North",
                    boundary_crossing=True,
                    risk_level="high",
                    status="resolved",
                    siren_activated=True,
                    sms_sent=True,
                    read=True,
                    title="Elephant herd crossing river trail",
                    created_at=now - timedelta(days=1, hours=7),
                ),
                models.Alert(
                    zone_id=restricted.id,
                    camera_id=cam3.id,
                    event_type=models.EventType.PERSON_DETECTED,
                    confidence=0.91,
                    species="Human",
                    movement_direction="Northwest",
                    boundary_crossing=False,
                    risk_level="medium",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=True,
                    read=True,
                    title="Unauthorized personnel near East boundary",
                    created_at=now - timedelta(days=2, hours=4),
                ),
                models.Alert(
                    zone_id=village1.id,
                    camera_id=cam1.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.94,
                    species="Lion",
                    movement_direction="South",
                    boundary_crossing=True,
                    risk_level="critical",
                    status="resolved",
                    siren_activated=True,
                    sms_sent=True,
                    read=True,
                    title="Lion tracking near village gate",
                    created_at=now - timedelta(days=2, hours=10),
                ),
                models.Alert(
                    zone_id=village2.id,
                    camera_id=cam2.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.78,
                    species="Deer",
                    movement_direction="West",
                    boundary_crossing=False,
                    risk_level="low",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=False,
                    read=True,
                    title="Spotted deer herd grazing",
                    created_at=now - timedelta(days=3, hours=3),
                ),
                models.Alert(
                    zone_id=village1.id,
                    camera_id=cam1.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.93,
                    species="Elephant",
                    movement_direction="North",
                    boundary_crossing=True,
                    risk_level="high",
                    status="resolved",
                    siren_activated=True,
                    sms_sent=True,
                    read=True,
                    title="Lone bull elephant near farm fence",
                    created_at=now - timedelta(days=3, hours=8),
                ),
                models.Alert(
                    zone_id=restricted.id,
                    camera_id=cam3.id,
                    event_type=models.EventType.PERSON_DETECTED,
                    confidence=0.87,
                    species="Human",
                    movement_direction="South-East",
                    boundary_crossing=False,
                    risk_level="medium",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=False,
                    read=True,
                    title="Gatherers spotted outside buffer line",
                    created_at=now - timedelta(days=4, hours=5),
                ),
                models.Alert(
                    zone_id=village1.id,
                    camera_id=cam1.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.89,
                    species="Leopard",
                    movement_direction="Northwest",
                    boundary_crossing=False,
                    risk_level="medium",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=True,
                    read=True,
                    title="Leopard prowl spotted in trees",
                    created_at=now - timedelta(days=4, hours=12),
                ),
                models.Alert(
                    zone_id=village2.id,
                    camera_id=cam2.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.76,
                    species="Wild Boar",
                    movement_direction="South",
                    boundary_crossing=False,
                    risk_level="low",
                    status="resolved",
                    siren_activated=False,
                    sms_sent=False,
                    read=True,
                    title="Wild boar feeding activity",
                    created_at=now - timedelta(days=5, hours=6),
                ),
                models.Alert(
                    zone_id=village1.id,
                    camera_id=cam1.id,
                    event_type=models.EventType.ANIMAL_DETECTED,
                    confidence=0.95,
                    species="Lion",
                    movement_direction="South-East",
                    boundary_crossing=True,
                    risk_level="critical",
                    status="resolved",
                    siren_activated=True,
                    sms_sent=True,
                    read=True,
                    title="Apex predator approach logged",
                    created_at=now - timedelta(days=5, hours=14),
                ),
            ]
            db.add_all(sample_alerts)

        db.commit()
        print("Seeded database successfully:")
        print(f"  • Zones: {db.query(models.Zone).count()}")
        print(f"  • Cameras: {db.query(models.Camera).count()}")
        print(f"  • Contacts: {db.query(models.Contact).count()}")
        print(f"  • Alerts: {db.query(models.Alert).count()}")
        print("  • Admin user: admin / changeme123")
    finally:
        db.close()


if __name__ == "__main__":
    reset_db = "--reset" in sys.argv
    run(reset=reset_db)
