"""
WildShield AI - Phase 2: Detection Rule Engine Test Suite
=========================================================
Automated unit tests covering all 15 required Phase 2 specifications:

1. Elephant detection -> Animal detection, ANIMAL_ALERT_REQUIRED, HIGH risk.
2. Deer detection -> Animal detection, ANIMAL_ALERT_REQUIRED.
3. Leopard detection -> Animal detection, ANIMAL_ALERT_REQUIRED, HIGH risk.
4. Wild boar detection -> Animal detection, ANIMAL_ALERT_REQUIRED (all string variants).
5. Human detection -> Human detection, HUMAN_NOTIFICATION_REQUIRED, no siren.
6. Peacock ignored -> Excluded class, siren not activated.
7. Low-confidence detection ignored -> Confidence below threshold.
8. Village A detection selects Village A siren -> 'Three short beeps followed by one long beep'.
9. Village B detection selects Village B siren -> 'Two long beeps followed by two short beeps'.
10. Human detection never activates siren -> Strict enforcement.
11. Duplicate detection suppression -> Track ID & spatial IoU suppression.
12. Siren cooldown -> Zone/incident cooldown prevents duplicate siren playback.
13. Unknown village handling -> Graceful fallback without crash.
14. Missing siren configuration handling -> Handled cleanly without crash.
15. Correct village and zone association -> Inherited from camera configuration.
"""

import os
import sys
import unittest

# Ensure project root and ai-model are on sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
ai_model_dir = os.path.join(project_root, "ai-model")
for p in (project_root, ai_model_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from detection_rules import (
    DetectionRuleEngine,
    RuleAction,
    ZoneType,
    ZoneConfig,
    Detection,
    RuleDecision,
    RiskAssessmentEngine,
    RiskLevel,
    SirenService,
    SirenStatus,
    VillageManager,
    VillageConfig,
    CameraConfig,
    compute_iou,
    normalize_class_name,
)


class TestPhase2DetectionRules(unittest.TestCase):

    def setUp(self):
        # Initialize isolated village manager and siren service (dry-run mode for silent testing)
        self.village_manager = VillageManager()
        self.siren_service = SirenService(default_cooldown_seconds=90.0, dry_run=True)
        self.risk_engine = RiskAssessmentEngine()

        self.engine = DetectionRuleEngine(
            default_confidence_threshold=0.60,
            default_cooldown_seconds=90.0,
            duplicate_window_seconds=10.0,
            village_manager=self.village_manager,
            siren_service=self.siren_service,
            risk_engine=self.risk_engine,
            dry_run_audio=True,
        )
        self.base_time = 1000.0

    # -----------------------------------------------------------------------
    # 1. Elephant Detection
    # -----------------------------------------------------------------------
    def test_01_elephant_detection(self):
        """Verify Elephant detection triggers ANIMAL_ALERT_REQUIRED and evaluates risk."""
        det = Detection(
            class_name="Elephant",
            confidence=0.94,
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.class_name, "Elephant")
        self.assertEqual(decision.risk_level, "HIGH")
        self.assertEqual(decision.action_text, "Animal alert required")
        self.assertEqual(decision.siren_status, "PLAYED")

        # Terminal output formatting verification (Module 9)
        output = decision.format_terminal()
        self.assertIn("[DETECTION] Elephant | Confidence: 94%", output)
        self.assertIn("[LOCATION] Village: Village A | Camera: CAM-001", output)
        self.assertIn("[ZONE] Forest Boundary", output)
        self.assertIn("[RISK] HIGH", output)
        self.assertIn("[ACTION] Animal alert required", output)
        self.assertIn("[SIREN] Village A sound selected", output)

    # -----------------------------------------------------------------------
    # 2. Deer Detection
    # -----------------------------------------------------------------------
    def test_02_deer_detection(self):
        """Verify Deer detection triggers ANIMAL_ALERT_REQUIRED."""
        det = Detection(
            class_name="deer",
            confidence=0.85,
            box=(50, 50, 150, 150),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.class_name, "Deer")
        self.assertIn(decision.risk_level, ["LOW", "MEDIUM"])
        self.assertEqual(decision.action_text, "Animal alert required")

    # -----------------------------------------------------------------------
    # 3. Leopard Detection
    # -----------------------------------------------------------------------
    def test_03_leopard_detection(self):
        """Verify Leopard detection triggers ANIMAL_ALERT_REQUIRED and evaluates as HIGH risk."""
        det = Detection(
            class_name="leopard",
            confidence=0.89,
            box=(80, 80, 220, 220),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(decision.class_name, "Leopard")
        self.assertEqual(decision.risk_level, "HIGH")
        self.assertEqual(decision.siren_status, "PLAYED")

    # -----------------------------------------------------------------------
    # 4. Wild Boar Detection
    # -----------------------------------------------------------------------
    def test_04_wild_boar_detection(self):
        """Verify Wild boar detection triggers ANIMAL_ALERT_REQUIRED for all naming variations."""
        for alias in ["Wild_boar", "wild boar", "wildboar", "Wild Boar"]:
            self.engine.reset_state()
            det = Detection(
                class_name=alias,
                confidence=0.78,
                box=(120, 120, 260, 260),
                timestamp=self.base_time,
                camera_id="CAM-001",
            )
            decision = self.engine.evaluate(det, current_time=self.base_time)

            self.assertTrue(decision.is_event)
            self.assertEqual(decision.action, RuleAction.ANIMAL_ALERT_REQUIRED)
            self.assertEqual(decision.class_name, "Wild_boar")
            self.assertEqual(decision.action_text, "Animal alert required")

    # -----------------------------------------------------------------------
    # 5. Human Detection
    # -----------------------------------------------------------------------
    def test_05_human_detection(self):
        """Verify Human detection triggers HUMAN_NOTIFICATION_REQUIRED without activating siren."""
        det = Detection(
            class_name="human",
            confidence=0.91,
            box=(200, 100, 350, 400),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(decision.class_name, "Human")
        self.assertEqual(decision.action_text, "Human detection recorded")
        self.assertEqual(decision.siren_status, "NOT_ACTIVATED")

        # Terminal output formatting verification (Module 9)
        output = decision.format_terminal()
        self.assertIn("[DETECTION] Human | Confidence: 91%", output)
        self.assertIn("[ACTION] Human detection recorded", output)
        self.assertIn("[SIREN] Not activated", output)

    # -----------------------------------------------------------------------
    # 6. Peacock Ignored
    # -----------------------------------------------------------------------
    def test_06_peacock_ignored(self):
        """Verify Peacock is excluded and ignored with reason 'Excluded class'."""
        det = Detection(
            class_name="Peacock",
            confidence=0.95,
            box=(50, 50, 150, 150),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertFalse(decision.is_event)
        self.assertEqual(decision.action, RuleAction.IGNORED)
        self.assertEqual(decision.reason, "Excluded class")
        self.assertEqual(
            decision.format_terminal(),
            "[IGNORED] Peacock | Reason: Excluded class",
        )

    # -----------------------------------------------------------------------
    # 7. Low-Confidence Detection Ignored
    # -----------------------------------------------------------------------
    def test_07_low_confidence_ignored(self):
        """Verify detections below threshold (0.60) are ignored."""
        det = Detection(
            class_name="Elephant",
            confidence=0.45,  # Below 0.60
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertFalse(decision.is_event)
        self.assertEqual(decision.action, RuleAction.IGNORED)
        self.assertEqual(decision.reason, "Confidence below threshold")
        self.assertEqual(
            decision.format_terminal(),
            "[IGNORED] Elephant | Reason: Confidence below threshold",
        )

    # -----------------------------------------------------------------------
    # 8. Village A Detection Selects Village A Siren
    # -----------------------------------------------------------------------
    def test_08_village_a_detection_selects_village_a_siren(self):
        """Verify camera in Village A selects Village A siren sound pattern."""
        # CAM-001 is registered to Village A
        det = Detection(
            class_name="Elephant",
            confidence=0.92,
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.village_id, "VIL-A")
        self.assertEqual(decision.village_name, "Village A")
        self.assertEqual(decision.siren_status, "PLAYED")
        self.assertEqual(decision.siren_pattern, "Three short beeps followed by one long beep")

        output = decision.format_terminal()
        self.assertIn("[LOCATION] Village: Village A | Camera: CAM-001", output)
        self.assertIn("[SIREN] Village A sound selected", output)

    # -----------------------------------------------------------------------
    # 9. Village B Detection Selects Village B Siren
    # -----------------------------------------------------------------------
    def test_09_village_b_detection_selects_village_b_siren(self):
        """Verify camera in Village B selects Village B siren sound pattern."""
        # CAM-002 is registered to Village B
        det = Detection(
            class_name="Elephant",
            confidence=0.93,
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-002",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.village_id, "VIL-B")
        self.assertEqual(decision.village_name, "Village B")
        self.assertEqual(decision.siren_status, "PLAYED")
        self.assertEqual(decision.siren_pattern, "Two long beeps followed by two short beeps")

        output = decision.format_terminal()
        self.assertIn("[LOCATION] Village: Village B | Camera: CAM-002", output)
        self.assertIn("[SIREN] Village B sound selected", output)

    # -----------------------------------------------------------------------
    # 10. Human Detection Never Activates Siren
    # -----------------------------------------------------------------------
    def test_10_human_detection_never_activates_siren(self):
        """Verify Human detections in any village or zone NEVER activate the siren."""
        for cam_id in ["CAM-001", "CAM-002", "CAM-003"]:
            self.engine.reset_state()
            det = Detection(
                class_name="Human",
                confidence=0.95,
                box=(100, 100, 200, 400),
                timestamp=self.base_time,
                camera_id=cam_id,
            )
            decision = self.engine.evaluate(det, current_time=self.base_time)

            self.assertTrue(decision.is_event)
            self.assertEqual(decision.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
            self.assertEqual(decision.siren_status, "NOT_ACTIVATED")
            self.assertIsNone(decision.siren_pattern)
            self.assertFalse(self.siren_service._active_playback)

            output = decision.format_terminal()
            self.assertIn("[SIREN] Not activated", output)

    # -----------------------------------------------------------------------
    # 11. Duplicate Detection Suppression
    # -----------------------------------------------------------------------
    def test_11_duplicate_detection_suppression(self):
        """Verify rapid repeated detections for the same object are suppressed."""
        # 11a. Track ID deduplication
        det1 = Detection(
            class_name="Elephant",
            confidence=0.90,
            box=(100, 100, 300, 300),
            track_id=101,
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec1 = self.engine.evaluate(det1, current_time=self.base_time)
        self.assertTrue(dec1.is_event)

        # Same track_id 2s later (within 10s duplicate window)
        det2 = Detection(
            class_name="Elephant",
            confidence=0.92,
            box=(105, 102, 305, 302),
            track_id=101,
            timestamp=self.base_time + 2.0,
            camera_id="CAM-001",
        )
        dec2 = self.engine.evaluate(det2, current_time=self.base_time + 2.0)
        self.assertFalse(dec2.is_event)
        self.assertEqual(dec2.action, RuleAction.IGNORED)
        self.assertIn("Duplicate detection suppressed", dec2.reason)

        # 11b. Spatial IoU deduplication when track_id is absent
        self.engine.reset_state()
        det_spatial1 = Detection(
            class_name="Deer",
            confidence=0.80,
            box=(100, 100, 200, 200),
            track_id=None,
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec_sp1 = self.engine.evaluate(det_spatial1, current_time=self.base_time)
        self.assertTrue(dec_sp1.is_event)

        det_spatial2 = Detection(
            class_name="Deer",
            confidence=0.82,
            box=(102, 101, 202, 201),  # High overlap (IoU > 0.3)
            track_id=None,
            timestamp=self.base_time + 1.0,
            camera_id="CAM-001",
        )
        dec_sp2 = self.engine.evaluate(det_spatial2, current_time=self.base_time + 1.0)
        self.assertFalse(dec_sp2.is_event)
        self.assertEqual(dec_sp2.action, RuleAction.IGNORED)
        self.assertIn("Duplicate detection suppressed", dec_sp2.reason)

    # -----------------------------------------------------------------------
    # 12. Siren Cooldown Behavior
    # -----------------------------------------------------------------------
    def test_12_siren_cooldown(self):
        """Verify alert cooldown suppresses repeated siren alerts until cooldown expires."""
        # First alert triggers event and siren
        det1 = Detection(
            class_name="Elephant",
            confidence=0.90,
            box=(100, 100, 300, 300),
            track_id=1,
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec1 = self.engine.evaluate(det1, current_time=self.base_time)
        self.assertTrue(dec1.is_event)
        self.assertEqual(dec1.siren_status, "PLAYED")

        # Second detection 30s later (within 90s cooldown)
        det2 = Detection(
            class_name="Elephant",
            confidence=0.92,
            box=(500, 500, 700, 700),  # Different location
            track_id=2,                  # Different track ID
            timestamp=self.base_time + 30.0,
            camera_id="CAM-001",
        )
        dec2 = self.engine.evaluate(det2, current_time=self.base_time + 30.0)
        self.assertFalse(dec2.is_event)
        self.assertEqual(dec2.action, RuleAction.IGNORED)
        self.assertIn("Alert cooldown active", dec2.reason)
        self.assertIn("60s remaining", dec2.reason)

        # After cooldown duration expires (t + 91s), alert triggers again
        det3 = Detection(
            class_name="Elephant",
            confidence=0.91,
            box=(520, 520, 720, 720),
            track_id=3,
            timestamp=self.base_time + 91.0,
            camera_id="CAM-001",
        )
        dec3 = self.engine.evaluate(det3, current_time=self.base_time + 91.0)
        self.assertTrue(dec3.is_event)
        self.assertEqual(dec3.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(dec3.siren_status, "PLAYED")

    # -----------------------------------------------------------------------
    # 13. Unknown Village Handling
    # -----------------------------------------------------------------------
    def test_13_unknown_village_handling(self):
        """Verify camera mapped to unknown village is handled gracefully without crash."""
        # Register a camera with non-existent village ID
        self.village_manager.register_camera(
            CameraConfig(
                camera_id="CAM-UNKNOWN-99",
                village_id="VIL-NONEXISTENT",
                zone_id="ZONE-UNKNOWN",
                status="ONLINE",
            )
        )

        det = Detection(
            class_name="Elephant",
            confidence=0.88,
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-UNKNOWN-99",
        )
        # Must not raise exception
        decision = self.engine.evaluate(det, current_time=self.base_time)

        self.assertTrue(decision.is_event)
        self.assertEqual(decision.siren_status, "UNKNOWN_VILLAGE")
        self.assertIsNone(decision.siren_pattern)
        self.assertEqual(decision.village_id, "VIL-NONEXISTENT")

    # -----------------------------------------------------------------------
    # 14. Missing Siren Configuration Handling
    # -----------------------------------------------------------------------
    def test_14_missing_siren_configuration_handling(self):
        """Verify village without configured siren is handled cleanly without crash."""
        # Create village without siren configuration
        vil_no_siren = VillageConfig(
            id="VIL-C",
            name="Village C (No Siren)",
            camera_ids=["CAM-004"],
            zone_ids=["ZONE-C-FB"],
            siren_config=None,  # Missing siren configuration
        )
        self.village_manager.register_village(vil_no_siren)
        self.village_manager.register_camera(
            CameraConfig(
                camera_id="CAM-004",
                village_id="VIL-C",
                zone_id="ZONE-C-FB",
                status="ONLINE",
            )
        )

        siren_result = self.siren_service.trigger_siren_for_village(vil_no_siren, current_time=self.base_time)
        self.assertEqual(siren_result.status, SirenStatus.MISSING_CONFIGURATION)
        self.assertFalse(siren_result.activated)
        self.assertIn("no configured siren", siren_result.message)

        # Also evaluate through rule engine
        det = Detection(
            class_name="Leopard",
            confidence=0.90,
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-004",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)
        self.assertTrue(decision.is_event)
        self.assertEqual(decision.siren_status, "MISSING_CONFIGURATION")

    # -----------------------------------------------------------------------
    # 15. Correct Village and Zone Association
    # -----------------------------------------------------------------------
    def test_15_village_and_zone_association(self):
        """
        Verify detection inherits village ID and zone ID from camera configuration,
        and never guesses geographic coordinates from animal images.
        """
        # Test Village A camera
        det_a = Detection(
            class_name="Elephant",
            confidence=0.91,
            box=(100, 100, 250, 250),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec_a = self.engine.evaluate(det_a, current_time=self.base_time)
        self.assertEqual(dec_a.village_id, "VIL-A")
        self.assertEqual(dec_a.village_name, "Village A")
        self.assertEqual(dec_a.zone_id, "ZONE-A-FB")
        self.assertEqual(dec_a.zone_name, "Forest Boundary")

        # Test Village B camera with same image detection
        self.engine.reset_state()
        det_b = Detection(
            class_name="Elephant",
            confidence=0.91,
            box=(100, 100, 250, 250),  # Identical detection box
            timestamp=self.base_time,
            camera_id="CAM-003",       # Registered to Village B / Agricultural Zone
        )
        dec_b = self.engine.evaluate(det_b, current_time=self.base_time)
        self.assertEqual(dec_b.village_id, "VIL-B")
        self.assertEqual(dec_b.village_name, "Village B")
        self.assertEqual(dec_b.zone_id, "ZONE-B-AG")
        self.assertEqual(dec_b.zone_name, "Agricultural Zone")

    # -----------------------------------------------------------------------
    # Additional Verification: Event Logging & Manual Stop Control
    # -----------------------------------------------------------------------
    def test_16_event_logging_records_all_fields(self):
        """Verify that Event Logger records all 10 mandatory Phase 2 fields."""
        det = Detection(
            class_name="Elephant",
            confidence=0.94,
            box=(100, 100, 300, 300),
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        decision = self.engine.evaluate(det, current_time=self.base_time)

        rec = self.engine.event_logger.get_latest()
        self.assertIsNotNone(rec)
        self.assertTrue(rec.event_id.startswith("EVT-"))
        self.assertEqual(rec.timestamp, self.base_time)
        self.assertEqual(rec.detection_class, "Elephant")
        self.assertEqual(rec.confidence, 0.94)
        self.assertEqual(rec.camera_id, "CAM-001")
        self.assertEqual(rec.village_id, "VIL-A")
        self.assertEqual(rec.zone_id, "ZONE-A-FB")
        self.assertEqual(rec.risk_level, "HIGH")
        self.assertEqual(rec.action_taken, "ANIMAL_ALERT_REQUIRED")
        self.assertEqual(rec.siren_config_selected, "Three short beeps followed by one long beep")
        self.assertEqual(rec.siren_playback_status, "PLAYED")

    def test_17_manual_siren_stop_control(self):
        """Verify manual stop control halts siren and returns valid status."""
        stop_result = self.siren_service.stop_siren()
        self.assertEqual(stop_result.status, SirenStatus.STOPPED)
        self.assertFalse(self.siren_service._active_playback)
        self.assertIn("Manual stop command executed", stop_result.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
