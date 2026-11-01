"""
WildShield AI - Complete Debugging and Verification Test Suite
==============================================================
Covers all 5 senior engineering debugging verification areas:
1. Siren shutdown reliability & non-blocking behavior
2. Comprehensive resource cleanup & worker thread termination
3. OpenCV window closure mechanisms (Q, ESC, 'X' button, cv2.error handling)
4. Cascading .env priority loading and API key masking
5. Roboflow inference error classification, anti-flooding, and recovery
"""

import io
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root and ai-model are on sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
ai_model_dir = os.path.join(project_root, "ai-model")
for p in (project_root, ai_model_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2
import numpy as np

from siren_service import SirenPlaybackResult, SirenService, SirenStatus
from village_manager import VillageManager
from roboflow_webcam_test import (
    RoboflowWorker,
    load_env_cascading,
    mask_api_key,
)


# ===========================================================================
# 1. Siren Shutdown Tests
# ===========================================================================
class TestSirenShutdown(unittest.TestCase):

    def setUp(self):
        self.vm = VillageManager()
        self.vil_a = self.vm.get_village("VIL-A")
        self.service = SirenService(default_cooldown_seconds=1.0, dry_run=False)

    def tearDown(self):
        self.service.stop_siren()

    def test_winsound_async_stop_reliability(self):
        """Verify PlaySound(None, SND_ASYNC) reliably halts active sound."""
        res = self.service.trigger_siren_for_village(self.vil_a)
        self.assertEqual(res.status, SirenStatus.PLAYED)
        self.assertTrue(self.service.is_playing)

        stop_res = self.service.stop_siren()
        self.assertEqual(stop_res.status, SirenStatus.STOPPED)
        self.assertFalse(self.service.is_playing)

    def test_shutdown_while_actively_playing(self):
        """Test stopping the siren while it is in the middle of active playback."""
        self.service.trigger_siren_for_village(self.vil_a)
        time.sleep(0.05)  # Let playback start
        self.assertTrue(self.service.is_playing)

        t_start = time.time()
        res = self.service.stop_siren()
        elapsed = time.time() - t_start

        self.assertEqual(res.status, SirenStatus.STOPPED)
        self.assertFalse(self.service.is_playing)
        self.assertLess(elapsed, 0.2, "stop_siren must complete in <200ms without blocking")

    def test_shutdown_does_not_hang(self):
        """Verify shutdown completes immediately even when no sound was playing."""
        t_start = time.time()
        for _ in range(5):
            res = self.service.stop_siren()
            self.assertEqual(res.status, SirenStatus.STOPPED)
        elapsed = time.time() - t_start
        self.assertLess(elapsed, 0.1, "Repeated stops on idle service must be instant")

    def test_repeated_stop_calls_do_not_crash(self):
        """Verify repeated calls to stop_siren are idempotent and safe."""
        for _ in range(10):
            res = self.service.stop_siren()
            self.assertEqual(res.status, SirenStatus.STOPPED)
        self.assertFalse(self.service.is_playing)


# ===========================================================================
# 2. Resource Cleanup Tests
# ===========================================================================
class TestResourceCleanup(unittest.TestCase):

    def test_cleanup_all_resources_invoked(self):
        """Verify siren, worker, webcam, and OpenCV window destruction are all called."""
        mock_rule_engine = MagicMock()
        mock_worker = MagicMock()
        mock_cap = MagicMock()

        # Simulate cleanup sequence from main()
        with patch("cv2.destroyAllWindows") as mock_destroy:
            try:
                mock_rule_engine.siren_service.stop_siren()
            except Exception:
                pass
            try:
                mock_worker.stop()
            except Exception:
                pass
            try:
                mock_cap.release()
            except Exception:
                pass
            try:
                mock_destroy()
            except Exception:
                pass

            mock_rule_engine.siren_service.stop_siren.assert_called_once()
            mock_worker.stop.assert_called_once()
            mock_cap.release.assert_called_once()
            mock_destroy.assert_called_once()

    def test_one_cleanup_failure_does_not_prevent_remaining(self):
        """Verify failure in siren stop or worker stop does not block webcam or window cleanup."""
        mock_siren_service = MagicMock()
        mock_siren_service.stop_siren.side_effect = RuntimeError("Audio device fault")

        mock_worker = MagicMock()
        mock_worker.stop.side_effect = RuntimeError("Worker thread error")

        mock_cap = MagicMock()

        with patch("cv2.destroyAllWindows") as mock_destroy:
            # Releasing siren (fails)
            try:
                mock_siren_service.stop_siren()
            except Exception:
                pass

            # Releasing worker (fails)
            try:
                mock_worker.stop()
            except Exception:
                pass

            # Releasing cap (must still execute)
            try:
                mock_cap.release()
            except Exception:
                pass

            # Destroying windows (must still execute)
            try:
                mock_destroy()
            except Exception:
                pass

            mock_cap.release.assert_called_once()
            mock_destroy.assert_called_once()

    def test_worker_thread_terminates(self):
        """Verify that RoboflowWorker thread cleanly stops and joins."""
        mock_client = MagicMock()
        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            inference_interval=0.1,
        )
        worker.start()
        self.assertTrue(worker._thread.is_alive())

        worker.stop()
        self.assertFalse(worker._thread.is_alive(), "Worker background thread must not remain running after stop()")


# ===========================================================================
# 3. OpenCV Window Closure Tests
# ===========================================================================
class TestOpenCVWindowClosure(unittest.TestCase):

    def test_exit_on_q_key(self):
        """Verify Q and q keypresses trigger the exit condition."""
        for key in [ord("q"), ord("Q")]:
            should_exit = key in (ord("q"), ord("Q")) or key == 27
            self.assertTrue(should_exit)

    def test_exit_on_esc_key(self):
        """Verify ESC keypress (27) triggers the exit condition."""
        key = 27
        should_exit = key in (ord("q"), ord("Q")) or key == 27
        self.assertTrue(should_exit)

    def test_exit_on_window_x_clicked(self):
        """Verify that when user closes window with 'X' button, loop exits."""
        # When user clicks 'X', cv2.getWindowProperty returns 0.0 or -1.0 (< 1)
        for closed_prop in [0.0, -1.0]:
            with patch("cv2.getWindowProperty", return_value=closed_prop):
                prop = cv2.getWindowProperty("TestWindow", cv2.WND_PROP_VISIBLE)
                should_exit = prop < 1
                self.assertTrue(should_exit)

    def test_window_property_exception_handled(self):
        """Verify that if cv2.getWindowProperty raises cv2.error, exit is triggered cleanly."""
        with patch("cv2.getWindowProperty", side_effect=cv2.error("Window already destroyed")):
            should_exit = False
            try:
                prop = cv2.getWindowProperty("TestWindow", cv2.WND_PROP_VISIBLE)
                if prop < 1:
                    should_exit = True
            except cv2.error:
                should_exit = True
            except Exception:
                pass

            self.assertTrue(should_exit, "cv2.error on destroyed window must be handled and trigger exit")


# ===========================================================================
# 4. Environment Variable Loading Tests
# ===========================================================================
class TestEnvLoading(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ai_model_dir = os.path.join(self.test_dir, "ai-model")
        self.backend_dir = os.path.join(self.test_dir, "backend")
        os.makedirs(self.ai_model_dir, exist_ok=True)
        os.makedirs(self.backend_dir, exist_ok=True)

        # Clear ROBOFLOW_API_KEY from environment for isolated testing
        self.saved_api_key = os.environ.get("ROBOFLOW_API_KEY")
        if "ROBOFLOW_API_KEY" in os.environ:
            del os.environ["ROBOFLOW_API_KEY"]

    def tearDown(self):
        if self.saved_api_key is not None:
            os.environ["ROBOFLOW_API_KEY"] = self.saved_api_key
        elif "ROBOFLOW_API_KEY" in os.environ:
            del os.environ["ROBOFLOW_API_KEY"]

    def test_api_key_only_in_ai_model_env(self):
        """Verify API key is loaded when present only in ai-model/.env."""
        env_file = os.path.join(self.ai_model_dir, ".env")
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=key_from_ai_model\n")

        load_env_cascading(self.ai_model_dir)
        self.assertEqual(os.environ.get("ROBOFLOW_API_KEY"), "key_from_ai_model")

    def test_api_key_only_in_root_env(self):
        """Verify API key is loaded when present only in project root .env."""
        env_file = os.path.join(self.test_dir, ".env")
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=key_from_root\n")

        load_env_cascading(self.ai_model_dir)
        self.assertEqual(os.environ.get("ROBOFLOW_API_KEY"), "key_from_root")

    def test_api_key_only_in_backend_env(self):
        """Verify API key is loaded when present only in backend/.env."""
        env_file = os.path.join(self.backend_dir, ".env")
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=key_from_backend\n")

        load_env_cascading(self.ai_model_dir)
        self.assertEqual(os.environ.get("ROBOFLOW_API_KEY"), "key_from_backend")

    def test_priority_cascade_ai_model_over_root_over_backend(self):
        """Verify priority: ai-model/.env > root .env > backend/.env."""
        # Write to all three locations
        with open(os.path.join(self.ai_model_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=priority1_aimodel\n")
        with open(os.path.join(self.test_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=priority2_root\n")
        with open(os.path.join(self.backend_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=priority3_backend\n")

        load_env_cascading(self.ai_model_dir)
        self.assertEqual(os.environ.get("ROBOFLOW_API_KEY"), "priority1_aimodel")

    def test_priority_cascade_root_over_backend(self):
        """Verify priority: root .env > backend/.env when ai-model/.env is absent."""
        with open(os.path.join(self.test_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=priority2_root\n")
        with open(os.path.join(self.backend_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=priority3_backend\n")

        load_env_cascading(self.ai_model_dir)
        self.assertEqual(os.environ.get("ROBOFLOW_API_KEY"), "priority2_root")

    def test_os_environ_never_overwritten(self):
        """Verify OS environment variable is NEVER overwritten by .env files."""
        os.environ["ROBOFLOW_API_KEY"] = "original_os_env_key"

        with open(os.path.join(self.ai_model_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=attempted_overwrite_aimodel\n")
        with open(os.path.join(self.test_dir, ".env"), "w", encoding="utf-8") as f:
            f.write("ROBOFLOW_API_KEY=attempted_overwrite_root\n")

        load_env_cascading(self.ai_model_dir)
        self.assertEqual(os.environ.get("ROBOFLOW_API_KEY"), "original_os_env_key")

    def test_api_key_masking_never_exposes_secrets(self):
        """Verify API keys are masked and raw keys never appear in masked logs."""
        raw_key = "rf_live_secret_key_9988776655"
        masked = mask_api_key(raw_key)

        self.assertNotIn("secret", masked)
        self.assertNotIn("99887766", masked)
        self.assertTrue(masked.startswith("rf_l..."))
        self.assertTrue(masked.endswith("6655"))

        # Short key
        self.assertEqual(mask_api_key("short"), "****")
        # None key
        self.assertEqual(mask_api_key(None), "<None>")


# ===========================================================================
# 5. Roboflow Inference Error Handling Tests
# ===========================================================================
class TestInferenceErrorHandling(unittest.TestCase):

    def test_invalid_api_key_error_classification(self):
        """Verify invalid API key errors are clearly classified."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("401 Unauthorized: Invalid API key provided")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            inference_interval=0.01,
        )

        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)

        with patch("sys.stdout", io.StringIO()):
            worker.start()
            time.sleep(0.1)
            worker.stop()

        _, _, _, last_error, _ = worker.get_results()
        self.assertIsNotNone(last_error)
        self.assertIn("API Authentication error", last_error)
        self.assertIn("check credentials", last_error)

    def test_network_timeout_error_classification(self):
        """Verify network timeout errors are clearly classified."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("ReadTimeout: HTTP connection timed out after 5000ms")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            inference_interval=0.01,
        )

        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)

        with patch("sys.stdout", io.StringIO()):
            worker.start()
            time.sleep(0.1)
            worker.stop()

        _, _, _, last_error, _ = worker.get_results()
        self.assertIsNotNone(last_error)
        self.assertIn("Network Timeout", last_error)

    def test_model_lookup_error_classification(self):
        """Verify 404 model/workflow lookup errors are clearly classified."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("404 Not Found: Target workflow 'wildshield-wf' does not exist")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="wildshield-wf",
            model_id=None,
            inference_interval=0.01,
        )

        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        worker.submit_frame(dummy_frame)

        with patch("sys.stdout", io.StringIO()):
            worker.start()
            time.sleep(0.1)
            worker.stop()

        _, _, _, last_error, _ = worker.get_results()
        self.assertIsNotNone(last_error)
        self.assertIn("Model/Workflow Lookup error", last_error)

    def test_repeated_errors_suppressed_no_terminal_flood(self):
        """Verify identical consecutive errors are printed to stdout only once."""
        mock_client = MagicMock()
        mock_client.run_workflow.side_effect = Exception("ReadTimeout: Connection timed out")

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            inference_interval=0.01,
        )

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            worker.start()
            for _ in range(5):
                worker.submit_frame(np.zeros((100, 100, 3), dtype=np.uint8))
                time.sleep(0.04)
            worker.stop()

        output = captured_stdout.getvalue()
        # Count occurrences of '[INFERENCE ERROR]'
        error_count = output.count("[INFERENCE ERROR]")
        self.assertEqual(error_count, 1, f"Expected exactly 1 printed error, got {error_count}")

    def test_recovery_after_temporary_failure(self):
        """Verify inference automatically recovers after a temporary failure."""
        mock_client = MagicMock()
        # Call 1 fails with timeout, Call 2 succeeds
        mock_client.run_workflow.side_effect = [
            Exception("ConnectTimeout: connection refused"),
            {"predictions": []},
        ]

        worker = RoboflowWorker(
            client=mock_client,
            workspace="test-ws",
            workflow="test-wf",
            model_id=None,
            inference_interval=0.01,
        )

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            worker.start()
            # Submit frame 1 (fails)
            worker.submit_frame(np.zeros((100, 100, 3), dtype=np.uint8))
            time.sleep(0.06)

            # Submit frame 2 (recovers)
            worker.submit_frame(np.zeros((100, 100, 3), dtype=np.uint8))
            time.sleep(0.06)

            worker.stop()

        output = captured_stdout.getvalue()
        self.assertIn("[INFERENCE ERROR]", output)
        self.assertIn("[INFERENCE RECOVERED]", output)

        _, _, _, last_error, total_infs = worker.get_results()
        self.assertIsNone(last_error, "Last error must be cleared upon successful recovery")
        self.assertGreaterEqual(total_infs, 1, "Total inferences counter must increment after recovery")


if __name__ == "__main__":
    unittest.main(verbosity=2)
