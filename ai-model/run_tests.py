"""
Launcher for Phase 2 Detection Rule Engine tests from within ai-model.
"""
import importlib.util
import os
import sys
import unittest

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
tests_file = os.path.join(project_root, "tests", "test_detection_rules.py")

for p in (project_root, script_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

spec = importlib.util.spec_from_file_location("root_test_detection_rules", tests_file)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TestPhase2DetectionRules = mod.TestPhase2DetectionRules

if __name__ == "__main__":
    unittest.main(verbosity=2)
