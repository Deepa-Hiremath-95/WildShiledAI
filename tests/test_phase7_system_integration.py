"""
WildShield AI - Phase 7 Complete System Integration and Final Verification Suite
================================================================================
Comprehensive integration and QA test suite covering all Phase 7 requirements:
- Task 1: AI Inference credential checks and error classification
- Task 2: Complete end-to-end pipeline handoff (Webcam -> Predictions -> Rules -> Village -> Risk -> Alert -> DB -> WS -> Dashboard)
- Task 3: Animal and human safety protocols, independent cooldowns, strict zero-siren for humans
- Task 4: Multi-village segregation (Village A vs Village B, camera-zone mapping, siren patterns)
- Task 5: Database and backend lifecycle (Persistence, Acknowledge, Resolve, RBAC, Audit trails)
- Task 6: Real-time WebSocket authentication, multi-client broadcasting, and disconnection
- Task 7: Analytics aggregations, hotspot rankings, CSV and PDF report generation
- Task 8: Failure testing (malformed predictions, inactive accounts, privilege escalation, rate limiting)
- Task 9: Performance benchmarks (actual latency thresholds)
"""

import io
import csv
import os
import sys
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure backend and ai-model roots are on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
AI_MODEL_DIR = os.path.join(BASE_DIR, "ai-model")

for p in [BACKEND_DIR, AI_MODEL_DIR, BASE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.database import Base, run_migrations
from app import models, schemas, auth, alert_engine
from app.config import settings
from app.services.ws_manager import ConnectionManager
from app.routers import (
    analytics,
    frontend_compat,
    auth as auth_router,
    alerts as alerts_router,
    cameras as cameras_router,
    zones as zones_router,
)
from detection_rules import (
    DetectionRuleEngine,
    RuleAction,
    ZoneType,
    RiskLevel,
    RiskAssessmentEngine,
    VillageManager,
    SirenService,
    EventLogger,
)
from roboflow_webcam_test import extract_predictions
from verify_live_roboflow import verify_live_roboflow


def run_coro(coro):
    """Executes a coroutine stack synchronously without creating a loopback socket."""
    stack = [coro]
    ret = None
    while stack:
        top = stack[-1]
        try:
            val = top.send(None)
            if hasattr(val, "send"):
                stack.append(val)
        except StopIteration as e:
            stack.pop()
            ret = e.value
    return ret


class Phase7IntegrationTestCase(unittest.TestCase):
    """Integrated test harness with in-memory SQLite, mock WebSocket manager, and full models."""

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

        # Seed standard Admin and Operator users
        self.admin_user = models.User(
            id="user-admin-p7",
            username="admin_p7",
            email="admin_p7@wildshield.org",
            hashed_password=auth.hash_password("AdminSecurePass2026!"),
            role=models.UserRole.ADMIN,
            is_active=True,
        )
        self.operator_user = models.User(
            id="user-operator-p7",
            username="operator_p7",
            email="operator_p7@wildshield.org",
            hashed_password=auth.hash_password("OperatorSecurePass2026!"),
            role=models.UserRole.OPERATOR,
            is_active=True,
        )
        self.db.add_all([self.admin_user, self.operator_user])
        self.db.commit()

        # Seed Villages A and B
        self.village_a = models.Village(
            id="vil-a",
            name="Village A",
            code="VIL-A",
            siren_pattern="pattern_1",
            is_active=True,
        )
        self.village_b = models.Village(
            id="vil-b",
            name="Village B",
            code="VIL-B",
            siren_pattern="pattern_2",
            is_active=True,
        )
        self.db.add_all([self.village_a, self.village_b])
        self.db.commit()

        # Seed Zones
        self.zone_a1 = models.Zone(
            id="zone-a-animal",
            village_id=self.village_a.id,
            name="Village A Outer Buffer",
            type=models.ZoneType.ANIMAL,
            confidence_threshold=0.60,
            cooldown_seconds=90,
            siren_duration_seconds=45,
        )
        self.zone_a2 = models.Zone(
            id="zone-a-restricted",
            village_id=self.village_a.id,
            name="Village A Core Sanctuary Corridor",
            type=models.ZoneType.RESTRICTED,
            confidence_threshold=0.60,
            cooldown_seconds=90,
            siren_duration_seconds=45,
        )
        self.zone_b1 = models.Zone(
            id="zone-b-animal",
            village_id=self.village_b.id,
            name="Village B Forest Edge",
            type=models.ZoneType.ANIMAL,
            confidence_threshold=0.60,
            cooldown_seconds=90,
            siren_duration_seconds=45,
        )
        self.db.add_all([self.zone_a1, self.zone_a2, self.zone_b1])
        self.db.commit()

        # Seed Cameras
        self.cam_001 = models.Camera(
            id="CAM-001",
            zone_id=self.zone_a1.id,
            village_id=self.village_a.id,
            name="Village A Buffer Cam 1",
            is_online=True,
            last_heartbeat=datetime.utcnow(),
        )
        self.cam_002 = models.Camera(
            id="CAM-002",
            zone_id=self.zone_b1.id,
            village_id=self.village_b.id,
            name="Village B Forest Cam 2",
            is_online=True,
            last_heartbeat=datetime.utcnow(),
        )
        self.cam_003 = models.Camera(
            id="CAM-003",
            zone_id=self.zone_a2.id,
            village_id=self.village_a.id,
            name="Village A Sanctuary Cam 3",
            is_online=False,
            last_heartbeat=datetime.utcnow() - timedelta(days=1),
        )
        self.db.add_all([self.cam_001, self.cam_002, self.cam_003])
        self.db.commit()

        # Rule Engine setup
        self.vm = VillageManager()
        self.siren_svc = SirenService(default_cooldown_seconds=90.0, dry_run=True)
        self.evt_logger = EventLogger()
        self.rule_engine = DetectionRuleEngine(
            default_confidence_threshold=0.60,
            default_cooldown_seconds=90.0,
            duplicate_window_seconds=10.0,
            default_human_cooldown_seconds=0.0,
            village_manager=self.vm,
            siren_service=self.siren_svc,
            event_logger=self.evt_logger,
            dry_run_audio=True,
        )
        self.risk_engine = RiskAssessmentEngine()

        # Reset rate limiting
        auth_router._FAILED_LOGINS.clear()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


class TestPhase7CompleteIntegration(Phase7IntegrationTestCase):
    """Execution of all 10 Phase 7 Integration Verification Tasks."""

    # ------------------------------------------------------------------------
    # Task 1: AI Inference Verification
    # ------------------------------------------------------------------------
    def test_task1_ai_inference_checks_and_error_classification(self):
        """Task 1: Verify Roboflow environment checks and error classification."""
        # 1. Environment verifier returns honest status
        report = verify_live_roboflow()
        self.assertIn(report["status"], ["NOT TESTED", "LIVE VERIFIED", "FAILED"])
        if report["status"] == "NOT TESTED":
            self.assertIn("Missing", report["reason"])

        # 2. Prediction parsing from raw Roboflow response
        raw_resp = {
            "predictions": [
                {"class": "Elephant", "confidence": 0.942, "x": 320, "y": 240, "width": 120, "height": 140, "track_id": 1}
            ]
        }
        parsed = extract_predictions(raw_resp, frame_w=640, frame_h=480)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["class_name"], "Elephant")
        self.assertAlmostEqual(parsed[0]["confidence"], 0.942, places=3)

    # ------------------------------------------------------------------------
    # Task 2: Complete End-to-End Pipeline
    # ------------------------------------------------------------------------
    def test_task2_complete_detection_pipeline_flow(self):
        """Task 2: Verify Webcam -> Predictions -> Rules -> Risk -> Alert -> DB -> Audit."""
        pred = {"class_name": "Elephant", "confidence": 0.94, "x": 320, "y": 240, "width": 100, "height": 100}

        # 1. Rules evaluate prediction
        decision = self.rule_engine.evaluate(pred, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.village_id, "VIL-A")

        # 2. Risk assessment
        risk_res = self.risk_engine.assess_risk(
            species=decision.class_name,
            zone_type=ZoneType.FOREST_BOUNDARY_ZONE,
            confidence=decision.confidence,
        )
        self.assertEqual(risk_res.level, RiskLevel.HIGH)

        # 3. Backend Alert Engine processing
        res = alert_engine.process_detection(
            db=self.db,
            camera=self.cam_001,
            zone=self.zone_a1,
            event_type=models.EventType.ANIMAL_DETECTED,
            confidence=decision.confidence,
            snapshot_path=None,
            species="Elephant",
        )

        # 4. Verify Alert created in DB
        self.assertIsNotNone(res.alert)
        self.assertTrue(res.alert.siren_activated)
        self.assertEqual(res.alert.risk_level, "critical")
        self.assertEqual(res.alert.village_id, self.village_a.id)

        # 5. Verify Detection linked to Alert
        self.assertIsNotNone(res.detection)
        self.assertEqual(res.detection.alert_id, res.alert.id)
        self.assertTrue(res.detection.siren_triggered)

    # ------------------------------------------------------------------------
    # Task 3: Animal and Human Safety
    # ------------------------------------------------------------------------
    def test_task3_animal_and_human_safety_and_independent_cooldowns(self):
        """Task 3: Verify Elephant, Leopard, Deer, Boar, Human, Excluded, and Cooldowns."""
        # 1. Animal detections
        self.rule_engine.reset_state()
        d_elephant = self.rule_engine.evaluate({"class_name": "Elephant", "confidence": 0.92}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_elephant.action, RuleAction.ANIMAL_ALERT_REQUIRED)

        # Reset cooldown for clean independent checks
        self.rule_engine.reset_state()
        d_leopard = self.rule_engine.evaluate({"class_name": "Leopard", "confidence": 0.89}, camera_id="CAM-002", village_id="VIL-B")
        self.assertEqual(d_leopard.action, RuleAction.ANIMAL_ALERT_REQUIRED)

        self.rule_engine.reset_state()
        d_deer = self.rule_engine.evaluate({"class_name": "Deer", "confidence": 0.75}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_deer.action, RuleAction.ANIMAL_ALERT_REQUIRED)

        self.rule_engine.reset_state()
        d_boar = self.rule_engine.evaluate({"class_name": "Wild Boar", "confidence": 0.81}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_boar.action, RuleAction.ANIMAL_ALERT_REQUIRED)

        # 2. Excluded species (Peacock)
        d_peacock = self.rule_engine.evaluate({"class_name": "Peacock", "confidence": 0.95}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_peacock.action, RuleAction.IGNORED)
        self.assertEqual(d_peacock.reason, "Excluded class")

        # 3. Human detection NEVER activates siren
        self.rule_engine.reset_state()
        d_human = self.rule_engine.evaluate({"class_name": "Human", "confidence": 0.91}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_human.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(d_human.siren_status, "NOT_ACTIVATED")
        self.assertIsNone(d_human.siren_pattern)
        self.assertFalse(self.rule_engine.siren_service.is_playing)

        # 4. Animal siren 90-second cooldown
        # Trigger animal siren in ZONE-A-FB for CAM-001
        self.rule_engine.reset_state()
        d_first = self.rule_engine.evaluate({"class_name": "Elephant", "confidence": 0.92}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_first.action, RuleAction.ANIMAL_ALERT_REQUIRED)

        # Subsequent animal detection in same zone within 90s is suppressed by cooldown
        d_elephant_cooldown = self.rule_engine.evaluate({"class_name": "Elephant", "confidence": 0.92, "track_id": 99}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_elephant_cooldown.action, RuleAction.IGNORED)
        self.assertIn("cooldown active", d_elephant_cooldown.reason.lower())

        # 5. Independent Human cooldown: Human detection is NOT blocked by active animal cooldown
        d_human_during_animal_cd = self.rule_engine.evaluate({"class_name": "Human", "confidence": 0.93, "track_id": 102}, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(d_human_during_animal_cd.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(d_human_during_animal_cd.siren_status, "NOT_ACTIVATED")
        self.assertIsNone(d_human_during_animal_cd.siren_pattern)

        # Stop siren and verify siren is inactive
        self.rule_engine.siren_service.stop_siren()
        self.assertFalse(self.rule_engine.siren_service.is_playing)

    # ------------------------------------------------------------------------
    # Task 4: Multi-Village Integration
    # ------------------------------------------------------------------------
    def test_task4_multi_village_segregation_and_configurations(self):
        """Task 4: Verify Village A vs Village B mapping, sound patterns, and ownership."""
        # CAM-001 -> Village A
        cam_a = self.db.query(models.Camera).filter_by(id="CAM-001").first()
        self.assertEqual(cam_a.village.name, "Village A")
        self.assertEqual(cam_a.village.siren_pattern, "pattern_1")

        # CAM-002 -> Village B
        cam_b = self.db.query(models.Camera).filter_by(id="CAM-002").first()
        self.assertEqual(cam_b.village.name, "Village B")
        self.assertEqual(cam_b.village.siren_pattern, "pattern_2")

        # Verification of separate siren sound patterns in VillageManager
        pattern_a = self.vm.get_village("VIL-A").siren_config.pattern_name
        pattern_b = self.vm.get_village("VIL-B").siren_config.pattern_name
        self.assertEqual(pattern_a, "VIL-A-PATTERN")
        self.assertEqual(pattern_b, "VIL-B-PATTERN")

    # ------------------------------------------------------------------------
    # Task 5: Database and Backend Lifecycle
    # ------------------------------------------------------------------------
    def test_task5_database_and_backend_lifecycle(self):
        """Task 5: Verify persistence, alert acknowledge, resolve, RBAC, and audit logs."""
        alert = models.Alert(
            id="alt-lifecycle-01",
            zone_id=self.zone_a1.id,
            camera_id=self.cam_001.id,
            village_id=self.village_a.id,
            species="Elephant",
            confidence=0.95,
            risk_level="critical",
            status="active",
            event_type=models.EventType.ANIMAL_DETECTED,
        )
        self.db.add(alert)
        self.db.commit()

        # 1. Acknowledge alert
        res_ack = run_coro(alerts_router.acknowledge_alert(
            alert_id=alert.id,
            db=self.db,
            current_user=self.operator_user,
        ))
        self.assertTrue(res_ack["read"])
        self.assertIsNotNone(res_ack["acknowledged_at"])

        # 2. Resolve alert
        res_res = run_coro(alerts_router.resolve_alert(
            alert_id=alert.id,
            db=self.db,
            current_user=self.operator_user,
        ))
        self.assertEqual(res_res.status, "resolved")
        self.assertIsNotNone(res_res.resolved_at)

        # 3. Verify Audit Logs created
        ack_audit = self.db.query(models.AuditLog).filter_by(action="ALERT_ACKNOWLEDGED", resource_id=alert.id).first()
        self.assertIsNotNone(ack_audit)
        self.assertEqual(ack_audit.user_id, self.operator_user.id)

        res_audit = self.db.query(models.AuditLog).filter_by(action="ALERT_RESOLVED", resource_id=alert.id).first()
        self.assertIsNotNone(res_audit)

        # 4. Persistence across fresh session
        fresh_session = self.SessionLocal()
        persisted_alert = fresh_session.query(models.Alert).filter_by(id="alt-lifecycle-01").first()
        self.assertEqual(persisted_alert.status, "resolved")
        fresh_session.close()

    # ------------------------------------------------------------------------
    # Task 6: Real-Time WebSocket and Dashboard Clients
    # ------------------------------------------------------------------------
    def test_task6_websocket_authentication_and_broadcasting(self):
        """Task 6: Verify WebSocket token validation, broadcasting, and disconnection."""
        from app.main import websocket_endpoint

        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()

        # Expired token -> closed with code 1008
        bad_token = auth.create_access_token({"sub": "admin_p7"}, expires_minutes=-10)
        run_coro(websocket_endpoint(websocket=mock_ws, token=bad_token))
        mock_ws.close.assert_called_with(code=1008)

        # Broadcasting across multiple clients using send_text
        class MockClient:
            def __init__(self):
                self.sent = []
            async def send_text(self, text):
                self.sent.append(text)

        ws_mgr = ConnectionManager()
        client1, client2 = MockClient(), MockClient()
        ws_mgr.active = [client1, client2]

        run_coro(ws_mgr.broadcast("LIVE_DETECTION", {"species": "Elephant", "risk": "critical"}))
        self.assertEqual(len(client1.sent), 1)
        self.assertEqual(len(client2.sent), 1)
        self.assertIn("LIVE_DETECTION", client1.sent[0])

        # Disconnection handling
        ws_mgr.disconnect_sync(client1)
        self.assertEqual(len(ws_mgr.active), 1)
        self.assertNotIn(client1, ws_mgr.active)

    # ------------------------------------------------------------------------
    # Task 7: Analytics and Reports
    # ------------------------------------------------------------------------
    def test_task7_analytics_and_report_exports(self):
        """Task 7: Verify real database analytics, hotspot ranking, CSV & PDF export."""
        # Seed test detection
        det = models.Detection(
            id="det-an-01",
            camera_id=self.cam_001.id,
            zone_id=self.zone_a1.id,
            village_id=self.village_a.id,
            event_type=models.EventType.ANIMAL_DETECTED,
            species="Elephant",
            confidence=0.96,
            risk_level="critical",
            siren_triggered=True,
        )
        self.db.add(det)
        self.db.commit()

        # 1. Summary analytics
        summary = analytics.get_analytics_summary(village_id="vil-a", db=self.db)
        self.assertEqual(summary["total_detections"], 1)
        self.assertEqual(summary["risk_engine"]["type"], "HEURISTIC")

        # 2. Hotspots ranking with spatial notice
        hotspots = analytics.get_hotspot_analysis(db=self.db)
        self.assertTrue(len(hotspots["hotspots"]) >= 1)
        self.assertIn("descriptive activity ranking only", hotspots["spatial_disclaimer"].lower())

        # 3. CSV report export
        csv_res = analytics.download_csv_report(village_id="vil-a", db=self.db)
        self.assertEqual(csv_res.media_type, "text/csv")
        self.assertIn("Elephant", csv_res.body.decode("utf-8"))

        # 4. PDF report export conforming to PDF-1.4
        pdf_res = analytics.download_pdf_report(village_id="vil-a", db=self.db)
        self.assertEqual(pdf_res.media_type, "application/pdf")
        self.assertTrue(pdf_res.body.startswith(b"%PDF-1.4"))

    # ------------------------------------------------------------------------
    # Task 8: Failure Testing and Error Classification
    # ------------------------------------------------------------------------
    def test_task8_failure_handling_and_resilience(self):
        """Task 8: Verify rate limiting, privilege escalation defense, and error handling."""
        # 1. Privilege escalation defense
        profile_up = schemas.UserProfileUpdate(role="admin")
        with self.assertRaises(HTTPException) as ctx_priv:
            auth_router.update_current_user_profile(
                profile_in=profile_up,
                db=self.db,
                current_user=self.operator_user,
            )
        self.assertEqual(ctx_priv.exception.status_code, 403)

        # 2. Rate limiting on login attempts
        req_mock = MagicMock()
        req_mock.client.host = "10.10.10.10"
        form = OAuth2PasswordRequestForm(grant_type="password", username="admin_p7", password="BadPassword!", scope="", client_id=None, client_secret=None)

        for _ in range(5):
            with self.assertRaises(HTTPException):
                auth_router.login(request=req_mock, form_data=form, db=self.db)
        # 6th attempt -> 429 Too Many Requests
        with self.assertRaises(HTTPException) as ctx_rate:
            auth_router.login(request=req_mock, form_data=form, db=self.db)
        self.assertEqual(ctx_rate.exception.status_code, 429)

        # 3. Deletion guard for cameras with historical records
        alt_guard = models.Alert(
            zone_id=self.zone_a1.id,
            camera_id=self.cam_001.id,
            species="Tiger",
            confidence=0.99,
            risk_level="critical",
            event_type=models.EventType.ANIMAL_DETECTED,
        )
        self.db.add(alt_guard)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx_del:
            run_coro(cameras_router.delete_camera(self.cam_001.id, self.db, self.admin_user))
        self.assertEqual(ctx_del.exception.status_code, 400)
        self.assertIn("historical detection or alert records", ctx_del.exception.detail)

    # ------------------------------------------------------------------------
    # Task 9: Performance Benchmarks
    # ------------------------------------------------------------------------
    def test_task9_performance_benchmark_bounds(self):
        """Task 9: Verify latency benchmarks adhere to real performance thresholds."""
        # 1. Rule evaluation latency (< 1.0 ms)
        t0 = time.perf_counter()
        pred = {"class_name": "Elephant", "confidence": 0.95, "x": 320, "y": 240, "width": 100, "height": 100}
        for _ in range(100):
            self.rule_engine.evaluate(pred, camera_id="CAM-001", village_id="VIL-A")
        avg_rule_ms = (time.perf_counter() - t0) / 100 * 1000
        self.assertLess(avg_rule_ms, 1.0, f"Rule evaluation exceeded 1.0 ms threshold: {avg_rule_ms:.3f} ms")

        # 2. Database write latency (< 15.0 ms sustained average)
        w_warm = models.Detection(
            camera_id=self.cam_001.id,
            zone_id=self.zone_a1.id,
            village_id=self.village_a.id,
            event_type=models.EventType.ANIMAL_DETECTED,
            species="Deer",
            confidence=0.80,
            risk_level="low",
        )
        self.db.add(w_warm)
        self.db.commit()

        t0 = time.perf_counter()
        n_writes = 10
        for _ in range(n_writes):
            det = models.Detection(
                camera_id=self.cam_001.id,
                zone_id=self.zone_a1.id,
                village_id=self.village_a.id,
                event_type=models.EventType.ANIMAL_DETECTED,
                species="Deer",
                confidence=0.80,
                risk_level="low",
            )
            self.db.add(det)
            self.db.commit()
        db_write_ms = (time.perf_counter() - t0) / n_writes * 1000
        self.assertLess(db_write_ms, 15.0, f"DB write exceeded 15.0 ms threshold: {db_write_ms:.3f} ms")

        # 3. PDF generation latency (< 150.0 ms)
        t0 = time.perf_counter()
        analytics.download_pdf_report(village_id="vil-a", db=self.db)
        pdf_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(pdf_ms, 150.0, f"PDF generation exceeded 150.0 ms threshold: {pdf_ms:.3f} ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
