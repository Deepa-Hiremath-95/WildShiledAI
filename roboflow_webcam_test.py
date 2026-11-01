"""
WildShield AI - Standalone Roboflow YOLOv11 Webcam Test (Root Launcher)
========================================================================
Delegates to ai-model/roboflow_webcam_test.py so the test can be launched
directly from the workspace root or from the ai-model/ directory.
"""
import importlib.util
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_ai_model_dir = os.path.join(_script_dir, "ai-model")
if _ai_model_dir not in sys.path:
    sys.path.insert(0, _ai_model_dir)

_ai_model_file = os.path.join(_ai_model_dir, "roboflow_webcam_test.py")

_spec = importlib.util.spec_from_file_location("ai_model_roboflow_webcam_test", _ai_model_file)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export key components
main = _mod.main
RoboflowWorker = _mod.RoboflowWorker
extract_predictions = _mod.extract_predictions
draw_ui_overlay = _mod.draw_ui_overlay
load_env_cascading = _mod.load_env_cascading
mask_api_key = _mod.mask_api_key
post_detection_to_backend = getattr(_mod, "post_detection_to_backend", None)

if __name__ == "__main__":
    main()
