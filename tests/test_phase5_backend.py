"""
WildShield AI - Phase 5 Backend Hardening Test Suite
===================================================
Comprehensive automated verification for Phase 5 deliverables:
1. Database Architecture & Persistence across all 9 models
2. CRUD Operations (Villages, Zones, Cameras)
3. Authentication & RBAC (Password Hashing, JWT, Operator vs Admin)
4. Complete Alert Lifecycle (Ingest -> Risk -> Alert -> Acknowledge -> Resolve)
5. Separation of Human & Animal Alerts (Siren Cooldown & Human Lockout Isolation)
6. System Settings Hierarchy & Persistence
7. WebSocket Event Broadcasting & Dead-Client Purging
8. Centralized Error Handling & Structured JSON Responses
9. Full Backward Compatibility for Frontend Endpoints
"""

import os
import sys
import uuid
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure backend root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.database import Base, run_migrations
from app import models, schemas, auth
from app.services.ws_manager import ConnectionManager
from app.routers import (
    villages,
    zones,
    cameras,
    alerts,
    settings as settings_router,
    frontend_compat,
)


def run_coro(coro):
    """Executes a coroutine synchronously without starting a loopback network socket."""
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


class Phase5BackendTestCase(unittest.TestCase):
    """Base test class providing an isolated in-memory SQLite database for every test."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        run_migrations(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        # Seed Admin and Operator users
        self.admin_user = models.User(
            id="user-admin-1",
            username="admin",
            email="admin@wildshield.org",
            hashed_password=auth.hash_password("AdminPass123!"),
            role=models.UserRole.ADMIN,
            is_active=True,
        )
        self.operator_user = models.User(
            id="user-operator-1",
            username="operator",
            email="operator@wildshield.org",
            hashed_password=auth.hash_password("OperatorPass123!"),
            role=models.UserRole.OPERATOR,
            is_active=True,
        )
        self.db.add_all([self.admin_user, self.operator_user])
        self.db.commit()

        # Tokens
        self.admin_token = auth.create_access_token({"sub": "admin", "role": "admin"})
        self.operator_token = auth.create_access_token({"sub": "operator", "role": "operator"})

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


class TestDatabaseArchitecture(Phase5BackendTestCase):
    """Task 1: Database Architecture and Persistence across all models."""

    def test_all_models_persistence_and_relationships(self):
        # 1. Village
        village = models.Village(
            name="Kumily Fringe Village",
            code="VIL-KUM-01",
            description="Border settlement near reserve buffer",
            siren_pattern="TWO_TONE_WARBLE",
            emergency_contact="+919876543210",
            latitude=11.685,
            longitude=76.620,
            is_active=True,
        )
        self.db.add(village)
        self.db.commit()
        self.db.refresh(village)
        self.assertIsNotNone(village.id)
        self.assertIsNotNone(village.created_at)

        # 2. Zone linked to Village
        zone = models.Zone(
            name="Zone A - Wildlife Corridor",
            type=models.ZoneType.ANIMAL,
            village_id=village.id,
            confidence_threshold=0.60,
            cooldown_seconds=90,
            siren_duration_seconds=45,
            siren_status=False,
        )
        self.db.add(zone)
        self.db.commit()
        self.db.refresh(zone)
        self.assertEqual(zone.village_id, village.id)
        self.assertEqual(zone.village.name, "Kumily Fringe Village")

        # 3. Camera linked to Zone and Village
        camera = models.Camera(
            id="CAM-KUM-01",
            name="North Ridge Trail Cam",
            zone_id=zone.id,
            village_id=village.id,
            stream_source="0",
            is_online=True,
            last_heartbeat=datetime.utcnow(),
        )
        self.db.add(camera)
        self.db.commit()
        self.db.refresh(camera)
        self.assertEqual(camera.village_id, village.id)
        self.assertTrue(camera.is_online)

        # 4. Alert linked to Camera, Zone, Village
        alert = models.Alert(
            camera_id=camera.id,
            zone_id=zone.id,
            village_id=village.id,
            title="Elephant Intrusion Detected",
            species="Elephant",
            risk_level="high",
            confidence=0.92,
            status="active",
            siren_activated=True,
            event_type=models.EventType.ANIMAL_DETECTED,
            acknowledged_by="operator",
            acknowledged_at=datetime.utcnow(),
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        self.assertEqual(alert.village_id, village.id)

        # 5. Detection linked to Camera, Zone, Village, and Alert
        detection = models.Detection(
            camera_id=camera.id,
            zone_id=zone.id,
            village_id=village.id,
            alert_id=alert.id,
            species="Elephant",
            confidence=0.92,
            risk_level="high",
            movement_direction="towards_village",
            boundary_crossing=True,
            siren_triggered=True,
            action_taken="ALARM_TRIGGERED",
            snapshot_path="/snapshots/elephant_01.jpg",
            event_type=models.EventType.ANIMAL_DETECTED,
        )
        self.db.add(detection)
        self.db.commit()
        self.db.refresh(detection)
        self.assertIsNotNone(detection.id)
        self.assertEqual(detection.camera.name, "North Ridge Trail Cam")
        self.assertEqual(detection.alert_id, alert.id)

        # 6. SystemSetting
        setting = models.SystemSetting(
            key="animal_siren_cooldown_seconds",
            value="90",
            description="Animal siren cooldown",
        )
        self.db.add(setting)
        self.db.commit()
        self.db.refresh(setting)
        self.assertEqual(setting.value, "90")

        # 7. AuditLog
        audit = models.AuditLog(
            user_id="operator",
            action="ACKNOWLEDGE_ALERT",
            resource_type="alert",
            resource_id=str(alert.id),
            details='{"reason": "Verified on live feed"}',
        )
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        self.assertIsNotNone(audit.id)
        self.assertEqual(audit.action, "ACKNOWLEDGE_ALERT")
        self.assertEqual(audit.entity_type, "alert")

        # 8. Contact
        contact = models.Contact(name="Forest Ranger Range 1", phone_number="+919876543219", role="ranger")
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        self.assertIsNotNone(contact.id)


class TestVillageCRUD(Phase5BackendTestCase):
    """Task 2 & 6: Village Management Endpoints."""

    def test_village_full_crud_lifecycle(self):
        # 1. Create Village (Admin)
        payload = schemas.VillageCreate(
            name="East Buffer Village",
            code="VIL-EAST-02",
            description="Agricultural buffer zone",
            siren_pattern="FAST_PULSE_CHIRP",
            emergency_contact="+919876543212",
            latitude=11.692,
            longitude=76.635,
        )
        created = run_coro(villages.create_village(payload, self.db, self.admin_user))
        self.assertIsNotNone(created["id"])
        self.assertEqual(created["name"], "East Buffer Village")
        self.assertEqual(created["code"], "VIL-EAST-02")
        village_id = created["id"]

        # 2. Get Village by ID
        fetched = villages.get_village(village_id, self.db)
        self.assertEqual(fetched["id"], village_id)
        self.assertEqual(fetched["siren_pattern"], "FAST_PULSE_CHIRP")

        # 3. List Villages
        all_villages = villages.list_villages(self.db)
        self.assertTrue(any(v["id"] == village_id for v in all_villages))

        # 4. Update Village
        update_in = schemas.VillageUpdate(description="Updated tea estate boundary", siren_pattern="HI_LO_ALERT")
        updated = run_coro(villages.update_village(village_id, update_in, self.db, self.admin_user))
        self.assertEqual(updated["description"], "Updated tea estate boundary")
        self.assertEqual(updated["siren_pattern"], "HI_LO_ALERT")

        # 5. Soft Delete Village
        run_coro(villages.delete_village(village_id, self.db, self.admin_user))
        after_del = villages.get_village(village_id, self.db)
        self.assertFalse(after_del["is_active"])

    def test_village_duplicate_code_rejection(self):
        payload = schemas.VillageCreate(name="Village 1", code="DUP-01")
        run_coro(villages.create_village(payload, self.db, self.admin_user))

        payload_dup = schemas.VillageCreate(name="Village 2", code="DUP-01")
        with self.assertRaises(HTTPException) as ctx:
            run_coro(villages.create_village(payload_dup, self.db, self.admin_user))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already exists", ctx.exception.detail)


class TestZoneAndCameraCRUD(Phase5BackendTestCase):
    """Task 2 & 6: Zone & Camera Management with Village Association."""

    def test_zone_and_camera_management(self):
        # 1. Create Village
        vil = models.Village(name="Sector Village", code="SEC-01", siren_pattern="PULSE")
        self.db.add(vil)
        self.db.commit()

        # 2. Create Zone
        zone_in = schemas.ZoneCreate(
            name="Zone Sector 1",
            type=models.ZoneType.ANIMAL,
            village_id=vil.id,
            confidence_threshold=0.65,
            cooldown_seconds=90,
            siren_duration_seconds=45,
        )
        created_zone = run_coro(zones.create_zone(zone_in, self.db, self.admin_user))
        self.assertEqual(created_zone.village_id, vil.id)

        # 3. Create Camera
        cam_in = schemas.CameraCreate(
            id="CAM-SEC-01",
            name="Sector Cam 1",
            zone_id=created_zone.id,
            village_id=vil.id,
            stream_source="0",
        )
        created_cam = run_coro(cameras.create_camera(cam_in, self.db, self.admin_user))
        self.assertEqual(created_cam.village_id, vil.id)
        self.assertEqual(created_cam.zone_id, created_zone.id)

        # 4. Camera Heartbeat & Online Calculation
        run_coro(cameras.heartbeat(created_cam.id, db=self.db))
        cam_db = self.db.query(models.Camera).filter_by(id=created_cam.id).first()
        self.assertTrue(cameras.compute_camera_online(cam_db))

        # Simulate expired heartbeat (>90s)
        cam_db.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
        self.db.commit()
        self.assertFalse(cameras.compute_camera_online(cam_db))


class TestAuthenticationAndRBAC(Phase5BackendTestCase):
    """Task 3: Authentication, JWT, and Role-Based Access Control."""

    def test_password_hashing_and_verification(self):
        pwd = "SecureWildlifeSecret2026!"
        hashed = auth.hash_password(pwd)
        self.assertTrue(auth.verify_password(pwd, hashed))
        self.assertFalse(auth.verify_password("WrongPassword!", hashed))

    def test_jwt_generation_and_validation(self):
        token = auth.create_access_token({"sub": "admin", "role": "admin"}, expires_minutes=15)
        user = auth.get_current_user(token=token, db=self.db)
        self.assertEqual(user.username, "admin")
        self.assertEqual(user.role, models.UserRole.ADMIN)

    def test_invalid_token_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            auth.get_current_user(token="invalid.malformed.token", db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_role_based_access_control(self):
        # Admin check passes
        admin_verified = auth.require_admin(self.admin_user)
        self.assertEqual(admin_verified.username, "admin")

        # Operator check raises 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            auth.require_admin(self.operator_user)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Admin access required", ctx.exception.detail)


class TestAlertManagementEngine(Phase5BackendTestCase):
    """Task 4: Alert Lifecycle & Strict Separation of Human and Animal Alerts."""

    def setUp(self):
        super().setUp()
        self.village = models.Village(
            name="Bandipur Buffer",
            code="BDP-01",
            siren_pattern="TWO_TONE_WARBLE",
            is_active=True,
        )
        self.db.add(self.village)
        self.db.commit()

        self.animal_zone = models.Zone(
            name="Zone A - Wildlife Corridor",
            type=models.ZoneType.ANIMAL,
            village_id=self.village.id,
            confidence_threshold=0.60,
            cooldown_seconds=90,
            siren_duration_seconds=45,
            siren_status=False,
        )
        self.restricted_zone = models.Zone(
            name="Zone B - Restricted Core",
            type=models.ZoneType.RESTRICTED,
            village_id=self.village.id,
            confidence_threshold=0.60,
            cooldown_seconds=90,
            siren_duration_seconds=45,
            siren_status=False,
        )
        self.db.add_all([self.animal_zone, self.restricted_zone])
        self.db.commit()

        self.cam_animal = models.Camera(
            id="CAM-CORRIDOR-01",
            name="Corridor Cam 1",
            zone_id=self.animal_zone.id,
            village_id=self.village.id,
            is_online=True,
            last_heartbeat=datetime.utcnow(),
        )
        self.cam_core = models.Camera(
            id="CAM-CORE-01",
            name="Core Cam 1",
            zone_id=self.restricted_zone.id,
            village_id=self.village.id,
            is_online=True,
            last_heartbeat=datetime.utcnow(),
        )
        self.db.add_all([self.cam_animal, self.cam_core])
        self.db.commit()

    @patch("app.routers.alerts.schedule_siren_auto_off")
    def test_animal_detection_activates_siren_and_enforces_90s_cooldown(self, mock_siren):
        mock_siren.return_value = MagicMock()
        payload = schemas.DetectionEvent(
            camera_id=self.cam_animal.id,
            event_type=models.EventType.ANIMAL_DETECTED,
            confidence=0.88,
            species="Elephant",
            movement_direction="towards_village",
            boundary_crossing=True,
        )

        # 1. Ingest Animal Detection
        alert = run_coro(alerts.ingest_detection(payload, self.db, _auth=None))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.species, "Elephant")
        self.assertIn(alert.risk_level, ["high", "critical"])
        self.assertTrue(alert.siren_activated)

        # Verify detection persisted in DB
        det = self.db.query(models.Detection).filter_by(camera_id=self.cam_animal.id).first()
        self.assertIsNotNone(det)
        self.assertEqual(det.species, "Elephant")
        self.assertTrue(det.siren_triggered)

        # 2. Immediate second animal detection should be suppressed by 90s cooldown
        payload2 = schemas.DetectionEvent(
            camera_id=self.cam_animal.id,
            event_type=models.EventType.ANIMAL_DETECTED,
            confidence=0.85,
            species="Elephant",
        )
        second_alert = run_coro(alerts.ingest_detection(payload2, self.db, _auth=None))
        # No new alert should be created during active cooldown
        self.assertIsNone(second_alert)

        # Verify detection record captures COOLDOWN_ACTIVE action
        det2 = self.db.query(models.Detection).order_by(models.Detection.created_at.desc()).first()
        self.assertIn("Animal Siren Cooldown", det2.action_taken)
        self.assertFalse(det2.siren_triggered)

    @patch("app.routers.alerts.schedule_siren_auto_off")
    def test_human_detection_never_activates_siren_and_bypasses_animal_cooldown(self, mock_siren):
        mock_siren.return_value = MagicMock()

        # 1. Trigger animal detection to activate animal siren cooldown
        animal_payload = schemas.DetectionEvent(
            camera_id=self.cam_animal.id,
            event_type=models.EventType.ANIMAL_DETECTED,
            confidence=0.90,
            species="Leopard",
        )
        run_coro(alerts.ingest_detection(animal_payload, self.db, _auth=None))

        # 2. Ingest Human Detection immediately while animal siren cooldown is active
        human_payload = schemas.DetectionEvent(
            camera_id=self.cam_core.id,
            event_type=models.EventType.PERSON_DETECTED,
            confidence=0.85,
            species="Person",
        )
        human_alert = run_coro(alerts.ingest_detection(human_payload, self.db, _auth=None))

        # INVARIANT VERIFICATION:
        # Human alert IS created (bypasses animal 90s cooldown!)
        self.assertIsNotNone(human_alert)
        # Human alert NEVER activates siren under any circumstance!
        self.assertFalse(human_alert.siren_activated)
        self.assertEqual(human_alert.species, "Person")

        # Verify detection record
        det_human = self.db.query(models.Detection).filter_by(camera_id=self.cam_core.id).first()
        self.assertIsNotNone(det_human)
        self.assertFalse(det_human.siren_triggered)
        self.assertIn("HUMAN_NOTIFICATION_REQUIRED", det_human.action_taken)

    def test_peacock_detection_excluded(self):
        peacock_payload = schemas.DetectionEvent(
            camera_id=self.cam_animal.id,
            event_type=models.EventType.ANIMAL_DETECTED,
            confidence=0.95,
            species="Peacock",
        )
        alert = run_coro(alerts.ingest_detection(peacock_payload, self.db, _auth=None))
        # Excluded species NEVER triggers an alert
        self.assertIsNone(alert)

        # Telemetry is recorded with IGNORED action
        det = self.db.query(models.Detection).filter_by(species="Peacock").first()
        self.assertIsNotNone(det)
        self.assertFalse(det.siren_triggered)
        self.assertIn("IGNORED (Excluded Species)", det.action_taken)

    def test_alert_acknowledge_and_resolve_lifecycle(self):
        # Create active alert
        alert = models.Alert(
            camera_id=self.cam_animal.id,
            zone_id=self.animal_zone.id,
            village_id=self.village.id,
            title="Wild Boar in corridor",
            species="Wild Boar",
            risk_level="medium",
            confidence=0.82,
            status="active",
            siren_activated=True,
            read=False,
            event_type=models.EventType.ANIMAL_DETECTED,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        # 1. Operator acknowledges alert
        ack_res = run_coro(alerts.toggle_alert_read(
            alert_id=alert.id,
            read_in=schemas.AlertReadUpdate(read=True),
            db=self.db,
            current_user=self.operator_user,
        ))
        self.assertTrue(ack_res["read"])
        self.assertEqual(ack_res["acknowledged_by"], "operator")
        self.assertIsNotNone(ack_res["acknowledged_at"])

        # 2. Operator resolves alert
        resolved_alert = run_coro(alerts.resolve_alert(
            alert_id=alert.id,
            resolve_in=schemas.AlertResolveUpdate(notes="Boar safely guided back to forest"),
            db=self.db,
            current_user=self.operator_user,
        ))
        self.assertEqual(resolved_alert.status, "resolved")
        self.assertEqual(resolved_alert.resolved_by, "operator")
        self.assertIsNotNone(resolved_alert.resolved_at)

        # 3. Verify AuditLog entries
        ack_audit = self.db.query(models.AuditLog).filter_by(action="ALERT_ACKNOWLEDGED", resource_id=str(alert.id)).first()
        self.assertIsNotNone(ack_audit)

        resolve_audit = self.db.query(models.AuditLog).filter_by(action="ALERT_RESOLVED", resource_id=str(alert.id)).first()
        self.assertIsNotNone(resolve_audit)
        self.assertIn("guided back to forest", resolve_audit.details)


class TestSystemSettingsAndAudit(Phase5BackendTestCase):
    """Task 7: Persistent Global System Settings and Audit History."""

    def test_system_settings_get_and_update(self):
        # 1. Read default settings
        current_settings = settings_router.get_system_settings(self.db)
        self.assertEqual(current_settings.animal_siren_cooldown_seconds, 90)
        self.assertEqual(current_settings.min_confidence, 0.60)

        # 2. Update settings (Admin required)
        update_in = schemas.SystemSettingsUpdate(
            animal_siren_cooldown_seconds=90,
            min_confidence=0.65,
            siren_duration_seconds=30,
        )
        updated = run_coro(settings_router.update_system_settings(
            update_in,
            self.db,
            self.admin_user,
        ))
        self.assertEqual(updated.animal_siren_cooldown_seconds, 90)
        self.assertEqual(updated.min_confidence, 0.65)

        # 3. Verify AuditLog was generated
        audit = self.db.query(models.AuditLog).filter_by(action="SETTINGS_UPDATED", user_id="user-admin-1").first()
        self.assertIsNotNone(audit)

    def test_audit_logs_pagination_and_filtering(self):
        # Populate audit logs
        for i in range(5):
            self.db.add(models.AuditLog(
                user_id="operator",
                action=f"ACTION_{i}",
                resource_type="alert",
                resource_id=f"alt-{i}",
            ))
        self.db.commit()

        logs = settings_router.list_audit_logs(
            skip=0,
            limit=3,
            db=self.db,
            current_user=self.admin_user,
        )
        self.assertEqual(len(logs), 3)


class TestWebSocketManager(unittest.TestCase):
    """Task 5: Thread-Safe WebSocket Push Manager & Event Broadcasting."""

    def test_broadcast_and_client_management(self):
        mgr = ConnectionManager()
        self.assertEqual(len(mgr.active), 0)

        # Create mock websockets
        ws_live = MagicMock()
        ws_live.accept = AsyncMock()
        ws_live.send_text = AsyncMock()

        ws_dead = MagicMock()
        ws_dead.accept = AsyncMock()
        ws_dead.send_text = AsyncMock(side_effect=Exception("Connection reset"))

        # Connect clients
        run_coro(mgr.connect(ws_live))
        run_coro(mgr.connect(ws_dead))
        self.assertEqual(len(mgr.active), 2)

        # Broadcast event -> dead client automatically purged without crashing
        run_coro(mgr.broadcast("new_detection", {"species": "Tiger", "confidence": 0.95}))
        ws_live.send_text.assert_called_once()
        self.assertEqual(len(mgr.active), 1)
        self.assertIn(ws_live, mgr.active)

        # Disconnect clean client
        run_coro(mgr.disconnect(ws_live))
        self.assertEqual(len(mgr.active), 0)


class TestCentralizedErrorHandling(Phase5BackendTestCase):
    """Task 8: Centralized Error Formatting & Clean JSON Responses."""

    def test_not_found_exception(self):
        with self.assertRaises(HTTPException) as ctx:
            villages.get_village("non-existent-id-9999", self.db)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Village not found", ctx.exception.detail)


class TestBackwardCompatibility(Phase5BackendTestCase):
    """Task 9: Backward Compatibility for Existing Frontend Dashboard."""

    def test_frontend_endpoints_data_shapes(self):
        # 1. Setup Village, Zone, Camera, Alert
        vil = models.Village(name="Village 1 (Kumily)", code="VIL-1", siren_pattern="PULSE")
        self.db.add(vil)
        self.db.commit()

        zone = models.Zone(name="Village 1 — Zone A", type=models.ZoneType.ANIMAL, village_id=vil.id)
        self.db.add(zone)
        self.db.commit()

        cam = models.Camera(id="CAM-001", name="North Ridge Cam", zone_id=zone.id, village_id=vil.id, is_online=True)
        self.db.add(cam)
        self.db.commit()

        alert = models.Alert(
            id="alert-compat-1",
            zone_id=zone.id,
            camera_id=cam.id,
            village_id=vil.id,
            species="Elephant",
            confidence=0.91,
            risk_level="high",
            status="active",
            siren_activated=True,
            read=False,
            title="Elephant near boundary",
            event_type=models.EventType.ANIMAL_DETECTED,
        )
        det = models.Detection(
            id="det-compat-1",
            camera_id=cam.id,
            zone_id=zone.id,
            village_id=vil.id,
            species="Elephant",
            confidence=0.91,
            risk_level="high",
            movement_direction="SE",
            boundary_crossing=True,
            siren_triggered=True,
            action_taken="ALARM_TRIGGERED",
            event_type=models.EventType.ANIMAL_DETECTED,
        )
        self.db.add_all([alert, det])
        self.db.commit()

        # 2. Test /api/active-alerts data contract
        active_alerts = frontend_compat.get_active_alerts(self.db)
        self.assertIsInstance(active_alerts, list)
        self.assertEqual(len(active_alerts), 1)
        a0 = active_alerts[0]
        self.assertIn("id", a0)
        self.assertIn("title", a0)
        self.assertIn("riskLevel", a0)
        self.assertIn("status", a0)
        self.assertIn("village", a0)
        self.assertIn("location", a0)
        self.assertIn("sirenActivated", a0)

        # 3. Test /api/detections data contract
        detections = frontend_compat.get_detections(self.db)
        self.assertIsInstance(detections, list)
        self.assertEqual(len(detections), 1)
        d0 = detections[0]
        self.assertIn("species", d0)
        self.assertIn("affectedVillage", d0)
        self.assertIn("location", d0)
        self.assertIn("sirenStatus", d0)
        self.assertIn("riskLevel", d0)

        # 4. Test /api/sirens data contract
        sirens = frontend_compat.get_sirens(self.db)
        self.assertIsInstance(sirens, list)

        # 5. Test /api/map-data contract
        map_data = frontend_compat.get_map_data(self.db)
        self.assertIn("threat", map_data)
        self.assertIn("zones", map_data)

        # 6. Test /api/analytics contract
        analytics = frontend_compat.get_analytics(self.db)
        self.assertIn("totalAlerts", analytics)
        self.assertIn("speciesCounts", analytics)


if __name__ == "__main__":
    unittest.main(verbosity=2)
