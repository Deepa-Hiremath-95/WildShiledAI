"""
Live Integration Verification Tests for WildShield AI Phase 2
=============================================================
Validates end-to-end integration contracts between:
- Roboflow prediction extraction
- detection_rules.py
- risk_engine.py
- village_manager.py (CAM-001 -> Village A, CAM-002 -> Village B)
- siren_service.py (Village-specific acoustic patterns & manual stop)
- event_logger.py (10 mandatory audit fields)
- OpenCV exit handlers and continuous webcam stream controls
"""

import os
import sys
import unittest

# Ensure ai-model directory is in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_ai_model_dir = os.path.abspath(os.path.join(_current_dir, "..", "ai-model"))
if _ai_model_dir not in sys.path:
    sys.path.insert(0, _ai_model_dir)

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
from roboflow_webcam_test import extract_predictions


class TestLiveIntegrationVerification(unittest.TestCase):
    """End-to-end live pipeline verification tests."""

    def setUp(self):
        self.village_mgr = VillageManager()
        self.siren_svc = SirenService(default_cooldown_seconds=90.0, dry_run=True)
        self.logger = EventLogger()
        self.engine = DetectionRuleEngine(
            default_confidence_threshold=0.60,
            default_cooldown_seconds=90.0,
            duplicate_window_seconds=10.0,
            village_manager=self.village_mgr,
            siren_service=self.siren_svc,
            event_logger=self.logger,
            dry_run_audio=True,
        )

    def test_01_prediction_extraction_and_routing_to_detection_rules(self):
        """Confirm that parsed predictions reach detection_rules.py evaluate()."""
        raw_roboflow_response = {
            "predictions": [
                {
                    "class": "Elephant",
                    "confidence": 0.94,
                    "x": 320,
                    "y": 240,
                    "width": 100,
                    "height": 100,
                    "track_id": 101,
                }
            ]
        }
        extracted = extract_predictions(raw_roboflow_response, frame_w=640, frame_h=480)
        self.assertEqual(len(extracted), 1)
        pred = extracted[0]
        self.assertEqual(pred["class_name"], "Elephant")
        self.assertAlmostEqual(pred["confidence"], 0.94, places=2)

        # Route through rule engine
        decision = self.engine.evaluate(pred, camera_id="CAM-001", village_id="VIL-A")
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.class_name, "Elephant")
        self.assertEqual(decision.village_id, "VIL-A")
        self.assertEqual(decision.camera_id, "CAM-001")
        self.assertTrue(decision.is_event)

    def test_02_risk_engine_evaluates_predictions(self):
        """Confirm that risk_engine.py evaluates predictions with risk levels."""
        risk_eng = RiskAssessmentEngine()
        # Elephant in Forest Boundary Zone should evaluate to HIGH risk
        eval_res = risk_eng.assess_risk(
            species="Elephant",
            zone_type=ZoneType.FOREST_BOUNDARY_ZONE,
            confidence=0.94,
            persistence_count=3,
            movement_direction="SE",
        )
        self.assertEqual(eval_res.level, RiskLevel.HIGH)
        self.assertIn("Elephant", eval_res.reasoning)
        self.assertGreaterEqual(eval_res.score, 0.70)

    def test_03_village_manager_assigns_correct_village_and_zone(self):
        """Confirm CAM-001 maps to Village A and CAM-002 maps to Village B."""
        cam1 = self.village_mgr.get_camera("CAM-001")
        self.assertIsNotNone(cam1)
        self.assertEqual(cam1.village_id, "VIL-A")
        self.assertEqual(cam1.zone_id, "ZONE-A-FB")

        cam2 = self.village_mgr.get_camera("CAM-002")
        self.assertIsNotNone(cam2)
        self.assertEqual(cam2.village_id, "VIL-B")
        self.assertEqual(cam2.zone_id, "ZONE-B-FB")

    def test_04_village_a_selects_village_a_siren(self):
        """Confirm Village A detection selects Village A siren sound pattern."""
        pred = {"class_name": "Elephant", "confidence": 0.92, "track_id": 201}
        decision = self.engine.evaluate(pred, camera_id="CAM-001")
        self.assertEqual(decision.village_name, "Village A")
        self.assertEqual(decision.village_id, "VIL-A")
        self.assertIn("Three short beeps", decision.siren_pattern or "")

    def test_05_village_b_selects_village_b_siren(self):
        """Confirm Village B detection selects Village B siren sound pattern."""
        pred = {"class_name": "Leopard", "confidence": 0.88, "track_id": 202}
        decision = self.engine.evaluate(pred, camera_id="CAM-002")
        self.assertEqual(decision.village_name, "Village B")
        self.assertEqual(decision.village_id, "VIL-B")
        self.assertIn("Two long beeps", decision.siren_pattern or "")

    def test_06_human_detection_does_not_activate_siren(self):
        """Confirm human detection produces notification but NEVER activates siren."""
        pred = {"class_name": "Human", "confidence": 0.91, "track_id": 301}
        decision = self.engine.evaluate(pred, camera_id="CAM-001")
        self.assertEqual(decision.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(decision.siren_status, "NOT_ACTIVATED")
        self.assertIn("Not activated", decision.format_terminal())

    def test_07_peacock_detection_is_ignored(self):
        """Confirm peacock detection is ignored with reason 'Excluded class'."""
        pred = {"class_name": "Peacock", "confidence": 0.85, "track_id": 401}
        decision = self.engine.evaluate(pred, camera_id="CAM-001")
        self.assertEqual(decision.action, RuleAction.IGNORED)
        self.assertEqual(decision.reason, "Excluded class")
        self.assertFalse(decision.is_event)

    def test_08_duplicate_suppression_and_cooldown_during_continuous_stream(self):
        """Confirm duplicate suppression and alert cooldown during continuous operation."""
        t0 = 1000.0
        pred = {"class_name": "Elephant", "confidence": 0.93, "track_id": 501}

        # First detection triggers alert
        d1 = self.engine.evaluate(pred, camera_id="CAM-001", current_time=t0)
        self.assertEqual(d1.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(d1.siren_status, "PLAYED")

        # Immediate next frame (same track_id within 10s window) is suppressed as duplicate
        d2 = self.engine.evaluate(pred, camera_id="CAM-001", current_time=t0 + 0.5)
        self.assertEqual(d2.action, RuleAction.IGNORED)
        self.assertIn("Duplicate", d2.reason or "")

        # New animal track after 15s (within 90s cooldown) is suppressed due to cooldown
        pred_new = {"class_name": "Deer", "confidence": 0.85, "track_id": 502}
        d3 = self.engine.evaluate(pred_new, camera_id="CAM-001", current_time=t0 + 15.0)
        self.assertEqual(d3.action, RuleAction.IGNORED)
        self.assertIn("Alert cooldown active", d3.reason or "")

        # After cooldown duration expires (t + 91s), alert triggers again
        pred_after = {"class_name": "Deer", "confidence": 0.88, "track_id": 503}
        d4 = self.engine.evaluate(pred_after, camera_id="CAM-001", current_time=t0 + 91.0)
        self.assertEqual(d4.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(d4.siren_status, "PLAYED")

    def test_09_event_logger_records_actual_events(self):
        """Confirm event_logger.py records all 10 mandatory fields."""
        pred = {"class_name": "Wild_boar", "confidence": 0.87, "track_id": 601}
        decision = self.engine.evaluate(pred, camera_id="CAM-001", current_time=2000.0)

        events = self.logger.get_all()
        self.assertGreaterEqual(len(events), 1)
        evt = events[-1].to_dict()

        mandatory_fields = [
            "event_id",
            "timestamp",
            "detection_class",
            "confidence",
            "camera_id",
            "village_id",
            "zone_id",
            "risk_level",
            "action_taken",
            "siren_config_selected",
            "siren_playback_status",
        ]
        for field in mandatory_fields:
            self.assertIn(field, evt, f"Missing field: {field}")
            self.assertIsNotNone(evt[field], f"Field {field} should not be None")

        self.assertEqual(evt["detection_class"], "Wild_boar")
        self.assertEqual(evt["camera_id"], "CAM-001")
        self.assertEqual(evt["village_id"], "VIL-A")

    def test_10_manual_siren_stop_control(self):
        """Confirm manual stop control halts siren."""
        pred = {"class_name": "Elephant", "confidence": 0.95, "track_id": 701}
        d = self.engine.evaluate(pred, camera_id="CAM-001")
        self.assertEqual(d.siren_status, "PLAYED")

        stop_result = self.siren_svc.stop_siren()
        self.assertEqual(stop_result.status, SirenStatus.STOPPED)
        self.assertIn("stopped", stop_result.message.lower())


if __name__ == "__main__":
    unittest.main()
