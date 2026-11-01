"""
WildShield AI - Phase 2: Detection Rule Engine (Root Launcher/Proxy)
===================================================================
Exports DetectionRuleEngine, RuleAction, ZoneType, Zone, ZoneConfig,
Detection, RuleDecision, RiskAssessmentEngine, RiskLevel, SirenService,
VillageManager, EventLogger, and helper functions from ai-model/detection_rules.py.
"""
import importlib.util
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_ai_model_dir = os.path.join(_script_dir, "ai-model")
if _ai_model_dir not in sys.path:
    sys.path.insert(0, _ai_model_dir)

_ai_model_file = os.path.join(_ai_model_dir, "detection_rules.py")

_spec = importlib.util.spec_from_file_location("ai_model_detection_rules", _ai_model_file)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["detection_rules"] = _mod
_spec.loader.exec_module(_mod)

# Core Rule Engine Exports
DetectionRuleEngine = _mod.DetectionRuleEngine
RuleAction = _mod.RuleAction
ZoneType = _mod.ZoneType
Zone = _mod.Zone
ZoneConfig = getattr(_mod, "ZoneConfig", _mod.Zone)
Detection = _mod.Detection
RuleDecision = _mod.RuleDecision
compute_iou = _mod.compute_iou
normalize_class_name = _mod.normalize_class_name
default_engine = _mod.default_engine

# Modular Subsystem Exports
from risk_engine import RiskAssessmentEngine, RiskAssessmentResult, RiskLevel
from siren_service import SirenPlaybackResult, SirenService, SirenStatus
from village_manager import CameraConfig, EmergencyContact, SirenConfig, VillageConfig, VillageManager
from event_logger import EventLogger, EventRecord

__all__ = [
    "DetectionRuleEngine",
    "RuleAction",
    "ZoneType",
    "Zone",
    "ZoneConfig",
    "Detection",
    "RuleDecision",
    "compute_iou",
    "normalize_class_name",
    "default_engine",
    "RiskAssessmentEngine",
    "RiskAssessmentResult",
    "RiskLevel",
    "SirenService",
    "SirenStatus",
    "SirenPlaybackResult",
    "VillageManager",
    "VillageConfig",
    "CameraConfig",
    "SirenConfig",
    "EmergencyContact",
    "EventLogger",
    "EventRecord",
]
