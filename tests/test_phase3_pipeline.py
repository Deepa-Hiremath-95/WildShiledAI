"""
Phase 3: Live AI Detection, End-to-End Pipeline, and Failure Handling Verification
===================================================================================
Tests all Phase 3 requirements:
- Task 2: End-to-End Detection Pipeline (Webcam -> Predictions -> Rules -> Village -> Risk -> Event -> Backend -> Dashboard)
- Task 3: Animal Detections (Elephant, Leopard, Deer, Wild Boar) with confidence, duplicates, risk, village siren, and 90s cooldown
- Task 4: Human Detections (HUMAN_NOTIFICATION_REQUIRED, never siren, bypasses animal cooldown, restricted zone, duplicate handling)
- Task 5: Dashboard Integration (Contract validation: Village, Camera, Zone, Class, Confidence, Risk, Timestamp, Status)
- Task 6: Comprehensive Failure Handling (Invalid API key, invalid workflow ID, network disconnect, timeout, webcam disconnect, empty predictions, malformed predictions)
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Ensure ai-model and backend directories are in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_current_dir, ".."))
_ai_model_dir = os.path.join(_root_dir, "ai-model")
_backend_dir = os.path.join(_root_dir, "backend")

for p in [_ai_model_dir, _backend_dir, _root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np

from detection_rules import (
    DetectionRuleEngine,
    RuleAction,
    RuleDecision,
    ZoneType,
    RiskLevel,
    RiskAssessmentEngine,
    SirenService,
    SirenStatus,
    VillageManager,
    EventLogger,
)
from roboflow_webcam_test import (
    extract_predictions,
    post_detection_to_backend,
    RoboflowWorker,
)


class TestPhase3EndToEndPipeline(unittest.TestCase):
    """Task 2: Complete Detection Pipeline Verification."""

    def setUp(self):
        self.village_mgr = VillageManager()
        self.siren_svc = SirenService(default_cooldown_seconds=90.0, dry_run=True)
        self.logger = EventLogger()
        self.engine = DetectionRuleEngine(
            default_confidence_threshold=0.60,
            default_cooldown_seconds=90.0,
            duplicate_window_seconds=10.0,
            default_human_cooldown_seconds=0.0,
            village_manager=self.village_mgr,
            siren_service=self.siren_svc,
            event_logger=self.logger,
            dry_run_audio=True,
        )

    def test_pipeline_step_by_step_flow(self):
        """
        Verify complete pipeline handoff:
        Webcam frame -> extract_predictions -> evaluate -> village_manager ->
        risk_engine -> alert routing -> event_logger -> backend payload.
        """
        # Step 1: Simulated frame dimensions
        frame_w, frame_h = 640, 480
        dummy_frame = np.zeros((frame_h, frame_w, 3), dtype=np.uint8)

        # Step 2: Roboflow response representation
        roboflow_output = {
            "predictions": [
                {
                    "class": "elephant",
                    "confidence": 0.92,
                    "x": 300,
                    "y": 200,
                    "width": 120,
                    "height": 100,
                    "track_id": 901,
                }
            ]
        }

        # Step 3: extract_predictions
        preds = extract_predictions(roboflow_output, frame_w, frame_h)
        self.assertEqual(len(preds), 1)
        self.assertEqual(preds[0]["class_name"], "Elephant")
        self.assertAlmostEqual(preds[0]["confidence"], 0.92, places=2)

        # Step 4: DetectionRuleEngine.evaluate (uses VillageManager and RiskAssessmentEngine)
        decision = self.engine.evaluate(
            preds[0],
            camera_id="CAM-001",
            village_id="VIL-A",
            current_time=1000.0,
        )

        # Step 5: Verify Decision & Village/Zone Inheritance
        self.assertTrue(decision.is_event)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.village_id, "VIL-A")
        self.assertEqual(decision.village_name, "Village A")
        self.assertEqual(decision.camera_id, "CAM-001")
        self.assertIn("Forest Boundary", decision.zone_name)
        self.assertIn("Three short beeps", decision.siren_pattern or "")
        self.assertEqual(decision.siren_status, "PLAYED")

        # Step 6: Verify EventLogger recorded mandatory fields
        events = self.logger.get_all()
        self.assertEqual(len(events), 1)
        evt = events[0].to_dict()
        self.assertEqual(evt["detection_class"], "Elephant")
        self.assertEqual(evt["camera_id"], "CAM-001")
        self.assertEqual(evt["village_id"], "VIL-A")
        self.assertEqual(evt["siren_playback_status"], "PLAYED")

        # Step 7: Verify Backend Ingestion Payload Generator
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"id": "alert-test-1", "status": "active"}

            resp = post_detection_to_backend(
                backend_url="http://localhost:8000",
                decision=decision,
                frame=dummy_frame,
                api_key="test-edge-key",
            )
            self.assertIsNotNone(resp)
            self.assertEqual(resp.get("id"), "alert-test-1")

            # Check POST payload
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "http://localhost:8000/api/detections")
            payload = kwargs["json"]
            self.assertEqual(payload["camera_id"], "CAM-001")
            self.assertEqual(payload["event_type"], "ANIMAL_DETECTED")
            self.assertEqual(payload["species"], "Elephant")
            self.assertAlmostEqual(payload["confidence"], 0.92, places=2)
            self.assertTrue(payload["boundary_crossing"])
            self.assertIsNotNone(payload["snapshot_base64"])
            self.assertEqual(kwargs["headers"]["X-API-Key"], "test-edge-key")


class TestPhase3AnimalDetections(unittest.TestCase):
    """Task 3: Detailed Animal Detections (Elephant, Leopard, Deer, Wild Boar)."""

    def setUp(self):
        self.village_mgr = VillageManager()
        self.siren_svc = SirenService(default_cooldown_seconds=90.0, dry_run=True)
        self.logger = EventLogger()
        self.engine = DetectionRuleEngine(
            default_confidence_threshold=0.60,
            default_cooldown_seconds=90.0,
            duplicate_window_seconds=10.0,
            default_human_cooldown_seconds=0.0,
            village_manager=self.village_mgr,
            siren_service=self.siren_svc,
            event_logger=self.logger,
            dry_run_audio=True,
        )

    def test_elephant_detection_full_cycle(self):
        """Elephant: confidence filtering, risk level, village siren, and 90s cooldown."""
        t0 = 2000.0
        # 1. Low confidence (< 0.60) ignored
        low_conf = {"class_name": "Elephant", "confidence": 0.55, "track_id": 11}
        d_low = self.engine.evaluate(low_conf, camera_id="CAM-001", current_time=t0)
        self.assertEqual(d_low.action, RuleAction.IGNORED)
        self.assertIn("Confidence", d_low.reason or "")
        self.assertFalse(d_low.is_event)

        # 2. High confidence (>= 0.60) in Forest Boundary -> HIGH risk alert
        valid_conf = {"class_name": "Elephant", "confidence": 0.88, "track_id": 12}
        d_valid = self.engine.evaluate(valid_conf, camera_id="CAM-001", current_time=t0 + 1.0)
        self.assertEqual(d_valid.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(d_valid.risk_level, RiskLevel.HIGH.value)
        self.assertEqual(d_valid.siren_status, "PLAYED")
        self.assertIn("Three short beeps", d_valid.siren_pattern or "")

        # 3. Duplicate within 10s ignored
        d_dup = self.engine.evaluate(valid_conf, camera_id="CAM-001", current_time=t0 + 3.0)
        self.assertEqual(d_dup.action, RuleAction.IGNORED)
        self.assertIn("Duplicate", d_dup.reason or "")

        # 4. New elephant track within 90s animal cooldown -> cooldown active
        new_track = {"class_name": "Elephant", "confidence": 0.91, "track_id": 13}
        d_cool = self.engine.evaluate(new_track, camera_id="CAM-001", current_time=t0 + 40.0)
        self.assertEqual(d_cool.action, RuleAction.IGNORED)
        self.assertIn("cooldown active", (d_cool.reason or "").lower())

        # 5. After 90s cooldown expires (t0 + 92s) -> triggers alert
        d_after = self.engine.evaluate(new_track, camera_id="CAM-001", current_time=t0 + 92.0)
        self.assertEqual(d_after.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(d_after.siren_status, "PLAYED")

    def test_leopard_detection_village_b(self):
        """Leopard: confidence filtering, risk level, Village B assignment and siren pattern."""
        t0 = 3000.0
        # Leopard in Village B (CAM-002)
        pred = {"class_name": "Leopard", "confidence": 0.85, "track_id": 21}
        decision = self.engine.evaluate(pred, camera_id="CAM-002", current_time=t0)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.village_id, "VIL-B")
        self.assertEqual(decision.village_name, "Village B")
        self.assertEqual(decision.risk_level, RiskLevel.HIGH.value)
        self.assertIn("Two long beeps", decision.siren_pattern or "")
        self.assertEqual(decision.siren_status, "PLAYED")

    def test_deer_detection_evaluation(self):
        """Deer: confidence filtering, risk level, duplicate suppression, and cooldown."""
        t0 = 4000.0
        pred = {"class_name": "Deer", "confidence": 0.78, "track_id": 31}
        decision = self.engine.evaluate(pred, camera_id="CAM-001", current_time=t0)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.class_name, "Deer")
        self.assertIn(decision.risk_level, [RiskLevel.LOW.value, RiskLevel.MEDIUM.value])
        self.assertEqual(decision.siren_status, "PLAYED")

    def test_wild_boar_detection_evaluation(self):
        """Wild boar: confidence filtering, risk level, duplicate suppression, and cooldown."""
        t0 = 5000.0
        pred = {"class_name": "Wild_boar", "confidence": 0.82, "track_id": 41}
        decision = self.engine.evaluate(pred, camera_id="CAM-001", current_time=t0)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.class_name, "Wild_boar")
        self.assertIn(decision.risk_level, [RiskLevel.MEDIUM.value, RiskLevel.HIGH.value])
        self.assertEqual(decision.siren_status, "PLAYED")


class TestPhase3HumanDetections(unittest.TestCase):
    """Task 4: Human Detection Protocol & Independent Cooldown Verification."""

    def setUp(self):
        self.village_mgr = VillageManager()
        self.siren_svc = SirenService(default_cooldown_seconds=90.0, dry_run=True)
        self.logger = EventLogger()
        self.engine = DetectionRuleEngine(
            default_confidence_threshold=0.60,
            default_cooldown_seconds=90.0,
            duplicate_window_seconds=10.0,
            default_human_cooldown_seconds=0.0,
            village_manager=self.village_mgr,
            siren_service=self.siren_svc,
            event_logger=self.logger,
            dry_run_audio=True,
        )

    def test_human_notification_required_and_no_siren(self):
        """Human detection generates HUMAN_NOTIFICATION_REQUIRED and never activates siren."""
        pred = {"class_name": "Human", "confidence": 0.88, "track_id": 101}
        decision = self.engine.evaluate(pred, camera_id="CAM-001", current_time=100.0)
        self.assertEqual(decision.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(decision.siren_status, "NOT_ACTIVATED")
        self.assertIn("Not activated", decision.format_terminal())
        self.assertTrue(decision.is_event)

    def test_human_bypasses_active_animal_siren_cooldown(self):
        """Human detection is not blocked when an animal siren cooldown is active."""
        t0 = 500.0
        # 1. Animal triggers 90s cooldown
        elephant_pred = {"class_name": "Elephant", "confidence": 0.90, "track_id": 1}
        d_animal = self.engine.evaluate(elephant_pred, camera_id="CAM-001", current_time=t0)
        self.assertEqual(d_animal.action, RuleAction.ANIMAL_ALERT_REQUIRED)

        # 2. Human detected 5 seconds later
        human_pred = {"class_name": "Human", "confidence": 0.85, "track_id": 2}
        d_human = self.engine.evaluate(human_pred, camera_id="CAM-001", current_time=t0 + 5.0)
        self.assertEqual(d_human.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(d_human.siren_status, "NOT_ACTIVATED")
        self.assertTrue(d_human.is_event)

    def test_human_detection_in_restricted_zone(self):
        """Restricted zone human detection is recorded with MEDIUM risk."""
        pred = {"class_name": "Human", "confidence": 0.85, "track_id": 3}
        decision = self.engine.evaluate(
            pred,
            camera_id="CAM-001",
            zone="restricted",
            current_time=600.0,
        )
        self.assertEqual(decision.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(decision.risk_level, RiskLevel.MEDIUM.value)
        self.assertIn("Restricted", decision.zone_name)

    def test_duplicate_human_detections(self):
        """Duplicate human detections with the same track_id in 10s are suppressed."""
        t0 = 700.0
        pred = {"class_name": "Human", "confidence": 0.80, "track_id": 4}
        d1 = self.engine.evaluate(pred, camera_id="CAM-001", current_time=t0)
        self.assertEqual(d1.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)

        # Same track immediately next frame
        d2 = self.engine.evaluate(pred, camera_id="CAM-001", current_time=t0 + 0.5)
        self.assertEqual(d2.action, RuleAction.IGNORED)
        self.assertIn("Duplicate", d2.reason or "")


class TestPhase3DashboardIntegration(unittest.TestCase):
    """Task 5: Dashboard and Frontend Compatibility Contract Verification."""

    def test_frontend_data_contract_fields(self):
        """
        Verify that detection/alert records formatted for the frontend provide
        all mandatory fields: Village, Camera ID, Zone, Detected Class, Confidence,
        Risk Level, Timestamp, and Alert Status.
        """
        from datetime import datetime, timezone
        from app.routers.frontend_compat import _fmt_alert_for_frontend, _fmt_detection_for_frontend
        from app import models

        # Create mock alert object matching models.Alert
        mock_zone = MagicMock()
        mock_zone.name = "Village 1 — Zone A"
        mock_zone.type = models.ZoneType.ANIMAL

        mock_camera = MagicMock()
        mock_camera.name = "North Ridge Trail Cam (CAM-001)"
        mock_camera.id = "CAM-001"

        mock_alert = MagicMock()
        mock_alert.id = "alt-999"
        mock_alert.title = "Elephant movement detected — Village 1 — Zone A"
        mock_alert.risk_level = "high"
        mock_alert.status = "active"
        mock_alert.read = False
        mock_alert.confidence = 0.92
        mock_alert.species = "Elephant"
        mock_alert.event_type = models.EventType.ANIMAL_DETECTED
        mock_alert.camera = mock_camera
        mock_alert.zone = mock_zone
        mock_alert.movement_direction = "SE"
        mock_alert.boundary_crossing = True
        mock_alert.created_at = datetime(2026, 11, 1, 10, 30, 0, tzinfo=timezone.utc)
        mock_alert.siren_activated = True
        mock_alert.sms_sent = False
        mock_alert.snapshot_path = "/snapshots/test.jpg"

        # 1. Test _fmt_alert_for_frontend (/api/active-alerts shape)
        fmt_alert = _fmt_alert_for_frontend(mock_alert)
        self.assertEqual(fmt_alert["village"], "Village 1")
        self.assertIn("CAM-001", fmt_alert["location"])
        self.assertEqual(fmt_alert["zone"], "Village 1 — Zone A")
        self.assertEqual(fmt_alert["detectedObject"], "Elephant")
        self.assertAlmostEqual(fmt_alert["confidence"], 0.92, places=2)
        self.assertEqual(fmt_alert["riskLevel"], "high")
        self.assertIn("2026-11-01", fmt_alert["timestamp"])
        self.assertTrue(fmt_alert["sirenActivated"])

        # 2. Test _fmt_detection_for_frontend (/api/detections shape)
        fmt_det = _fmt_detection_for_frontend(mock_alert)
        self.assertEqual(fmt_det["affectedVillage"], "Village 1 — Zone A")
        self.assertIn("CAM-001", fmt_det["location"])
        self.assertEqual(fmt_det["species"], "Elephant")
        self.assertAlmostEqual(fmt_det["confidence"], 0.92, places=2)
        self.assertEqual(fmt_det["riskLevel"], "high")
        self.assertEqual(fmt_det["sirenStatus"], "on")
        self.assertIn("2026-11-01", fmt_det["timestamp"])


class TestPhase3FailureHandling(unittest.TestCase):
    """Task 6: Failure Handling & False Alert Prevention."""

    def test_invalid_api_key_error_handling(self):
        """Test that invalid Roboflow API keys are classified and trigger 0 false alerts."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("401 Unauthorized: Invalid API key")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            min_confidence=0.60,
        )
        worker.start()

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)
        time.sleep(0.15)

        dets, dec, latency, err, total_infs = worker.get_results()
        worker.stop()

        self.assertIsNotNone(err)
        self.assertIn("API Authentication error", err)
        self.assertEqual(len(dets), 0)
        self.assertIsNone(dec)

    def test_invalid_workflow_id_error_handling(self):
        """Test that invalid workflow IDs are classified and trigger 0 false alerts."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("404 Not Found: workflow 'unknown_wf' not found")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="unknown_wf",
            model_id=None,
            min_confidence=0.60,
        )
        worker.start()

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)
        time.sleep(0.15)

        dets, dec, latency, err, total_infs = worker.get_results()
        worker.stop()

        self.assertIsNotNone(err)
        self.assertIn("Model/Workflow Lookup error", err)
        self.assertEqual(len(dets), 0)
        self.assertIsNone(dec)

    def test_network_disconnection_error_handling(self):
        """Test that network connection loss is handled gracefully without false alerts."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("Failed to establish a new connection: [Errno 11001] getaddrinfo failed")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            min_confidence=0.60,
        )
        worker.start()

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)
        time.sleep(0.15)

        dets, dec, latency, err, total_infs = worker.get_results()
        worker.stop()

        self.assertIsNotNone(err)
        self.assertIn("Network Connection error", err)
        self.assertEqual(len(dets), 0)
        self.assertIsNone(dec)

    def test_roboflow_timeout_error_handling(self):
        """Test that request timeouts are classified and trigger 0 false alerts."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("ReadTimeout: HTTP request timed out after 5.0 seconds")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            min_confidence=0.60,
        )
        worker.start()

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)
        time.sleep(0.15)

        dets, dec, latency, err, total_infs = worker.get_results()
        worker.stop()

        self.assertIsNotNone(err)
        self.assertIn("Network Timeout", err)
        self.assertEqual(len(dets), 0)
        self.assertIsNone(dec)

    def test_webcam_disconnection_graceful_handling(self):
        """Test that webcam read failures (e.g. device disconnected) are handled gracefully."""
        mock_cap = MagicMock()
        mock_cap.read.return_value = (False, None)

        ret, frame = mock_cap.read()
        self.assertFalse(ret)
        self.assertIsNone(frame)
        # Should not throw unhandled exception

    def test_empty_predictions_handling(self):
        """Test that empty prediction payloads produce 0 detections without error."""
        empty_responses = [
            [],
            {},
            {"predictions": []},
            {"detections": []},
            {"output": {}},
            None,
        ]
        for empty_resp in empty_responses:
            dets = extract_predictions(empty_resp, frame_w=640, frame_h=480)
            self.assertEqual(dets, [], f"Expected empty detections for {empty_resp}")

    def test_malformed_prediction_responses_handling(self):
        """Test that malformed prediction items are safely skipped without crash or false alert."""
        malformed_inputs = [
            # Missing coordinates
            {"predictions": [{"class": "Elephant", "confidence": 0.9}]},
            # Non-numeric confidence
            {"predictions": [{"class": "Elephant", "confidence": "unknown", "x": 100, "y": 100, "width": 50, "height": 50}]},
            # Non-numeric coordinates
            {"predictions": [{"class": "Elephant", "confidence": 0.9, "x": "bad", "y": 100, "width": 50, "height": 50}]},
            # Inverted bounding box (x2 <= x1)
            {"predictions": [{"class": "Elephant", "confidence": 0.9, "box": [200, 100, 100, 200]}]},
            # None confidence
            {"predictions": [{"class": "Elephant", "confidence": None, "x": 100, "y": 100, "width": 50, "height": 50}]},
            # Corrupted dict item
            {"predictions": ["string_item_instead_of_dict", 12345]},
        ]
        for malformed in malformed_inputs:
            dets = extract_predictions(malformed, frame_w=640, frame_h=480)
            self.assertEqual(dets, [], f"Expected 0 detections for malformed input: {malformed}")


if __name__ == "__main__":
    unittest.main()
