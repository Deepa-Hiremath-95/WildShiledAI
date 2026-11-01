"""
Alert Cooldown and Human Notification Verification Tests for WildShield AI
==========================================================================
Validates that:
1. Human detections never activate the animal siren.
2. Human detections are not suppressed by the animal siren cooldown.
3. Human detections in restricted zones are recorded independently.
4. Human detections follow HUMAN_NOTIFICATION_REQUIRED.
5. Peacock detections remain excluded under all conditions.
6. Animal detections retain their existing duplicate suppression and 90-second siren cooldown.
7. Duplicate human detections are handled appropriately via track ID and spatial IoU.
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
    Detection,
    DetectionRuleEngine,
    EventLogger,
    RiskAssessmentEngine,
    RiskLevel,
    RuleAction,
    RuleDecision,
    SirenService,
    SirenStatus,
    VillageManager,
    ZoneConfig,
    ZoneType,
)


class TestAlertCooldownLogic(unittest.TestCase):
    """Unit tests for independent cooldown and human notification logic."""

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
        self.base_time = 1000.0

    def test_01_human_detection_during_active_animal_cooldown(self):
        """Verify that human detections are NOT suppressed by an ongoing animal siren cooldown."""
        # 1. Animal detection triggers alert and 90-second cooldown in ZONE-A-FB
        det_elephant = Detection(
            class_name="Elephant",
            confidence=0.92,
            box=(100, 100, 300, 300),
            track_id=1,
            timestamp=self.base_time,
            camera_id="CAM-001",  # Assigned to ZONE-A-FB in Village A
        )
        dec_elephant = self.engine.evaluate(det_elephant, current_time=self.base_time)
        self.assertTrue(dec_elephant.is_event)
        self.assertEqual(dec_elephant.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(dec_elephant.siren_status, "PLAYED")

        # 2. Human detected 20 seconds later (well within the 90s animal cooldown)
        det_human = Detection(
            class_name="Human",
            confidence=0.88,
            box=(150, 150, 250, 350),
            track_id=2,
            timestamp=self.base_time + 20.0,
            camera_id="CAM-001",
        )
        dec_human = self.engine.evaluate(det_human, current_time=self.base_time + 20.0)

        # Human detection MUST NOT be suppressed by the animal cooldown
        self.assertTrue(dec_human.is_event)
        self.assertEqual(dec_human.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(dec_human.class_name, "Human")
        self.assertEqual(dec_human.siren_status, "NOT_ACTIVATED")
        self.assertNotIn("Alert cooldown active", dec_human.reason or "")

        # 3. Second animal detected 30 seconds after first animal (60s remaining on animal cooldown)
        det_elephant_2 = Detection(
            class_name="Elephant",
            confidence=0.90,
            box=(400, 400, 600, 600),
            track_id=3,
            timestamp=self.base_time + 30.0,
            camera_id="CAM-001",
        )
        dec_elephant_2 = self.engine.evaluate(det_elephant_2, current_time=self.base_time + 30.0)

        # Animal detection MUST retain its 90s cooldown
        self.assertFalse(dec_elephant_2.is_event)
        self.assertEqual(dec_elephant_2.action, RuleAction.IGNORED)
        self.assertIn("Alert cooldown active", dec_elephant_2.reason or "")
        self.assertIn("60s remaining", dec_elephant_2.reason or "")

    def test_02_multiple_consecutive_human_detections(self):
        """Verify multiple consecutive human detections are recorded and not locked out."""
        # Consecutive human detections with different tracks
        for idx in range(1, 5):
            t = self.base_time + (idx * 2.0)
            det = Detection(
                class_name="Human",
                confidence=0.85 + (idx * 0.02),
                box=(100 + idx * 10, 100, 200 + idx * 10, 300),
                track_id=f"human-track-{idx}",
                timestamp=t,
                camera_id="CAM-001",
            )
            dec = self.engine.evaluate(det, current_time=t)
            self.assertTrue(dec.is_event, f"Human detection {idx} was incorrectly ignored!")
            self.assertEqual(dec.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
            self.assertEqual(dec.siren_status, "NOT_ACTIVATED")

        # Verify all 4 were recorded in event logger
        events = [e for e in self.logger.get_all() if e.detection_class == "Human"]
        self.assertEqual(len(events), 4)

    def test_03_human_detection_in_restricted_zone(self):
        """Verify human detection in restricted zones is recorded with MEDIUM risk independently."""
        # Restricted Zone (ZONE-A-RES)
        cam_res = self.village_mgr.assign_camera("CAM-RES-01", "VIL-A", "ZONE-A-RES")
        det_human_res = Detection(
            class_name="Human",
            confidence=0.92,
            box=(100, 100, 250, 400),
            track_id="res-track-1",
            timestamp=self.base_time,
            camera_id="CAM-RES-01",
        )
        dec = self.engine.evaluate(det_human_res, current_time=self.base_time)

        self.assertTrue(dec.is_event)
        self.assertEqual(dec.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
        self.assertEqual(dec.risk_level, "MEDIUM")
        self.assertEqual(dec.zone_id, "ZONE-A-RES")
        self.assertEqual(dec.zone_name, "Restricted Zone")
        self.assertEqual(dec.siren_status, "NOT_ACTIVATED")
        self.assertFalse(self.siren_svc._active_playback)

        # Check logged record
        latest_event = self.logger.get_latest()
        self.assertIsNotNone(latest_event)
        self.assertEqual(latest_event.detection_class, "Human")
        self.assertEqual(latest_event.risk_level, "MEDIUM")
        self.assertEqual(latest_event.zone_id, "ZONE-A-RES")
        self.assertEqual(latest_event.action_taken, "HUMAN_NOTIFICATION_REQUIRED")

    def test_04_human_detection_never_activates_siren(self):
        """Verify that human detections across all zones never activate acoustic playback."""
        all_zones = [
            ("ZONE-A-FB", "Forest Boundary"),
            ("ZONE-A-AG", "Agricultural Zone"),
            ("ZONE-A-VB", "Village Boundary"),
            ("ZONE-A-RES", "Restricted Zone"),
            ("ZONE-A-FZ", "Forest Zone"),
        ]

        for z_id, z_name in all_zones:
            det = Detection(
                class_name="Human",
                confidence=0.95,
                box=(100, 100, 200, 400),
                track_id=f"track-{z_id}",
                timestamp=self.base_time,
                camera_id="CAM-001",
            )
            dec = self.engine.evaluate(det, zone=z_id, current_time=self.base_time)
            self.assertTrue(dec.is_event)
            self.assertEqual(dec.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)
            self.assertEqual(dec.siren_status, "NOT_ACTIVATED")
            self.assertIsNone(dec.siren_pattern)
            self.assertFalse(self.siren_svc._active_playback)
            self.assertIn("[SIREN] Not activated", dec.format_terminal())

    def test_05_animal_detection_retains_90_second_cooldown(self):
        """Verify animal alerts strictly retain the 90-second cooldown."""
        # T0: Initial animal alert triggers siren
        det1 = Detection(
            class_name="Elephant",
            confidence=0.91,
            box=(100, 100, 300, 300),
            track_id=10,
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec1 = self.engine.evaluate(det1, current_time=self.base_time)
        self.assertTrue(dec1.is_event)
        self.assertEqual(dec1.siren_status, "PLAYED")

        # T0 + 45s: Leopard detected in same zone (different track) -> suppressed by cooldown
        det2 = Detection(
            class_name="Leopard",
            confidence=0.89,
            box=(400, 400, 600, 600),
            track_id=11,
            timestamp=self.base_time + 45.0,
            camera_id="CAM-001",
        )
        dec2 = self.engine.evaluate(det2, current_time=self.base_time + 45.0)
        self.assertFalse(dec2.is_event)
        self.assertEqual(dec2.action, RuleAction.IGNORED)
        self.assertIn("Alert cooldown active (45s remaining)", dec2.reason or "")

        # T0 + 89s: Wild boar detected in same zone -> suppressed (1s remaining)
        det3 = Detection(
            class_name="Wild_boar",
            confidence=0.85,
            box=(200, 200, 350, 350),
            track_id=12,
            timestamp=self.base_time + 89.0,
            camera_id="CAM-001",
        )
        dec3 = self.engine.evaluate(det3, current_time=self.base_time + 89.0)
        self.assertFalse(dec3.is_event)
        self.assertIn("1s remaining", dec3.reason or "")

        # T0 + 91s: Deer detected in same zone -> cooldown expired, alert triggered
        det4 = Detection(
            class_name="Deer",
            confidence=0.86,
            box=(300, 300, 450, 450),
            track_id=13,
            timestamp=self.base_time + 91.0,
            camera_id="CAM-001",
        )
        dec4 = self.engine.evaluate(det4, current_time=self.base_time + 91.0)
        self.assertTrue(dec4.is_event)
        self.assertEqual(dec4.action, RuleAction.ANIMAL_ALERT_REQUIRED)
        self.assertEqual(dec4.siren_status, "PLAYED")

    def test_06_duplicate_human_detections_handled_appropriately(self):
        """Verify that duplicate human detections are appropriately suppressed."""
        # 6a. Same track ID within duplicate window (10s)
        det_h1 = Detection(
            class_name="Human",
            confidence=0.90,
            box=(100, 100, 200, 300),
            track_id="human-track-42",
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec_h1 = self.engine.evaluate(det_h1, current_time=self.base_time)
        self.assertTrue(dec_h1.is_event)

        # Same track 2 seconds later -> suppressed as duplicate
        det_h2 = Detection(
            class_name="Human",
            confidence=0.91,
            box=(102, 101, 202, 301),
            track_id="human-track-42",
            timestamp=self.base_time + 2.0,
            camera_id="CAM-001",
        )
        dec_h2 = self.engine.evaluate(det_h2, current_time=self.base_time + 2.0)
        self.assertFalse(dec_h2.is_event)
        self.assertEqual(dec_h2.action, RuleAction.IGNORED)
        self.assertIn("Duplicate detection suppressed (track_id human-track-42 active)", dec_h2.reason or "")

        # Same track after duplicate window expires (11s later) -> processed as new notification
        det_h3 = Detection(
            class_name="Human",
            confidence=0.92,
            box=(105, 102, 205, 302),
            track_id="human-track-42",
            timestamp=self.base_time + 11.0,
            camera_id="CAM-001",
        )
        dec_h3 = self.engine.evaluate(det_h3, current_time=self.base_time + 11.0)
        self.assertTrue(dec_h3.is_event)
        self.assertEqual(dec_h3.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)

        # 6b. Spatial IoU deduplication for untracked detections (track_id=None)
        self.engine.reset_state()
        det_sp1 = Detection(
            class_name="Human",
            confidence=0.88,
            box=(100, 100, 200, 300),
            track_id=None,
            timestamp=self.base_time,
            camera_id="CAM-001",
        )
        dec_sp1 = self.engine.evaluate(det_sp1, current_time=self.base_time)
        self.assertTrue(dec_sp1.is_event)

        # High spatial overlap (IoU > 0.30) 1s later -> suppressed
        det_sp2 = Detection(
            class_name="Human",
            confidence=0.89,
            box=(105, 102, 205, 302),
            track_id=None,
            timestamp=self.base_time + 1.0,
            camera_id="CAM-001",
        )
        dec_sp2 = self.engine.evaluate(det_sp2, current_time=self.base_time + 1.0)
        self.assertFalse(dec_sp2.is_event)
        self.assertEqual(dec_sp2.action, RuleAction.IGNORED)
        self.assertIn("Duplicate detection suppressed", dec_sp2.reason or "")

        # Different spatial location (IoU = 0.0) 1s later -> processed as independent event
        det_sp3 = Detection(
            class_name="Human",
            confidence=0.87,
            box=(500, 500, 600, 700),
            track_id=None,
            timestamp=self.base_time + 1.0,
            camera_id="CAM-001",
        )
        dec_sp3 = self.engine.evaluate(det_sp3, current_time=self.base_time + 1.0)
        self.assertTrue(dec_sp3.is_event)
        self.assertEqual(dec_sp3.action, RuleAction.HUMAN_NOTIFICATION_REQUIRED)

    def test_07_peacock_detections_remain_excluded_under_all_conditions(self):
        """Verify peacock detections are always excluded and ignored."""
        # 1. Idle state
        p1 = Detection(class_name="Peacock", confidence=0.95, timestamp=self.base_time)
        dec1 = self.engine.evaluate(p1, current_time=self.base_time)
        self.assertFalse(dec1.is_event)
        self.assertEqual(dec1.action, RuleAction.IGNORED)
        self.assertEqual(dec1.reason, "Excluded class")

        # 2. During active animal cooldown
        self.engine.set_zone_cooldown("ZONE-A-FB", self.base_time)
        p2 = Detection(class_name="peacock", confidence=0.99, timestamp=self.base_time + 5.0)
        dec2 = self.engine.evaluate(p2, current_time=self.base_time + 5.0)
        self.assertFalse(dec2.is_event)
        self.assertEqual(dec2.action, RuleAction.IGNORED)
        self.assertEqual(dec2.reason, "Excluded class")


if __name__ == "__main__":
    unittest.main()

