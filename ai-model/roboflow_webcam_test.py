"""
WildShield AI - Phase 2: Standalone Roboflow YOLOv11 Webcam Test + Rule Engine
================================================================================
Connects laptop webcam to your trained Roboflow workflow / YOLOv11 model
and integrates the Phase 2 Detection Rule Engine.

Phase 2 Features:
- Dedicated asynchronous background worker to prevent webcam feed stutter.
- Rate-limiting & latency awareness (configurable inference FPS, default 2 FPS).
- Configurable Village Management:
    * Select Demonstration Village A or Village B via `--village`
    * Camera & Zone association via `--camera-id`
- Modular Detection Rule Engine:
    * Animal alerts: Elephant, Deer, Leopard, Wild_boar -> Animal alert required
    * Human notifications: Human -> Human detection recorded (siren NEVER activated)
    * Excluded classes: Peacock -> Ignored
    * Configurable confidence threshold (default 0.60)
    * Duplicate detection prevention (track_id and spatial/temporal IoU)
    * Alert cooldown prevention for ongoing incidents (default 90s)
    * 5 Supported Zones: Forest Zone, Forest Boundary, Agricultural, Village Boundary, Restricted
- Risk Assessment Engine:
    * 3 Risk Levels: LOW, MEDIUM, HIGH
    * Multi-frame persistence tracking
    * Movement direction evaluation strictly when tracking info is available
- Village-Specific Laptop Siren Selection:
    * Village A: 3 short beeps + 1 long beep
    * Village B: 2 long beeps + 2 short beeps
    * Manual Stop Control via 'S' key
- Clean exit via 'Q' key.
"""

import argparse
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Cascading Environment Variable Loader
# ---------------------------------------------------------------------------
def load_env_cascading(script_dir: Optional[str] = None) -> List[str]:
    """
    Loads environment variables with strict priority:
    1. ai-model/.env
    2. Project root .env
    3. backend/.env
    Existing operating-system environment variables are NEVER overwritten (override=False).
    Returns list of paths successfully loaded.
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))

    candidates = [
        os.path.join(script_dir, ".env"),
        os.path.join(project_root, ".env"),
        os.path.join(project_root, "backend", ".env"),
    ]

    loaded: List[str] = []
    try:
        from dotenv import load_dotenv
        for env_file in candidates:
            if os.path.isfile(env_file):
                load_dotenv(env_file, override=False)
                loaded.append(env_file)
    except ImportError:
        pass
    return loaded


def mask_api_key(api_key: Optional[str]) -> str:
    """Masks API key to prevent exposing secrets in logs."""
    if not api_key:
        return "<None>"
    return f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"


# Execute cascading environment load upon module import
load_env_cascading()

# Import official Roboflow Inference SDK
try:
    from inference_sdk import InferenceHTTPClient, InferenceConfiguration
except ImportError:
    InferenceHTTPClient = None
    InferenceConfiguration = None

# Import Phase 2 Detection Rule Engine and Subsystems
from detection_rules import (
    DetectionRuleEngine,
    RuleAction,
    RuleDecision,
    ZoneType,
    ZoneConfig,
    Detection,
    RiskAssessmentEngine,
    RiskLevel,
    SirenService,
    SirenStatus,
    VillageManager,
    VillageConfig,
    CameraConfig,
    normalize_class_name as normalize_rule_class,
)


# ---------------------------------------------------------------------------
# Supported Classes & UI Colors (BGR format for OpenCV)
# ---------------------------------------------------------------------------
SUPPORTED_CLASSES = {
    "elephant": {"display": "Elephant", "color": (255, 191, 0)},     # Deep Sky Blue
    "deer": {"display": "Deer", "color": (50, 205, 50)},             # Lime Green
    "human": {"display": "Human", "color": (0, 165, 255)},           # Bright Orange
    "person": {"display": "Human", "color": (0, 165, 255)},          # COCO alias for human
    "leopard": {"display": "Leopard", "color": (204, 50, 153)},      # Purple / Magenta
    "wild_boar": {"display": "Wild_boar", "color": (0, 69, 255)},    # Crimson / Red-Orange
    "wild boar": {"display": "Wild_boar", "color": (0, 69, 255)},    # Alias
    "wildboar": {"display": "Wild_boar", "color": (0, 69, 255)},     # Alias
    "peacock": {"display": "Peacock", "color": (209, 206, 0)},       # Bright Cyan / Teal
}

DEFAULT_COLOR = (180, 180, 180)  # Fallback gray for other classes


def get_class_display_and_color(raw_name: str) -> Tuple[str, Tuple[int, int, int]]:
    """Map raw class string to supported class display name and BGR color."""
    key = raw_name.strip().lower()
    if key in SUPPORTED_CLASSES:
        entry = SUPPORTED_CLASSES[key]
        return entry["display"], entry["color"]
    return raw_name.strip().capitalize(), DEFAULT_COLOR


# ---------------------------------------------------------------------------
# Prediction Extractor
# ---------------------------------------------------------------------------
def extract_predictions(response: Any, frame_w: int, frame_h: int) -> List[Dict[str, Any]]:
    """
    Extracts bounding boxes, labels, and confidences from Roboflow workflow/model responses.
    Hardened against malformed, partial, or missing fields.
    """
    detections: List[Dict[str, Any]] = []

    if not response:
        return detections

    candidate = response[0] if isinstance(response, list) and len(response) > 0 else response

    items_to_scan: List[Any] = []
    if isinstance(candidate, dict):
        for key in ["predictions", "detections", "output", "model_predictions", "results"]:
            if key in candidate and isinstance(candidate[key], list):
                items_to_scan = candidate[key]
                break
            elif key in candidate and isinstance(candidate[key], dict):
                inner = candidate[key]
                if "predictions" in inner and isinstance(inner["predictions"], list):
                    items_to_scan = inner["predictions"]
                    break
        if not items_to_scan:
            for v in candidate.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and ("confidence" in v[0] or "class" in v[0]):
                    items_to_scan = v
                    break
                elif isinstance(v, dict) and "predictions" in v and isinstance(v["predictions"], list):
                    items_to_scan = v["predictions"]
                    break
    elif isinstance(candidate, list):
        items_to_scan = candidate

    for item in items_to_scan:
        if not isinstance(item, dict):
            continue

        try:
            raw_class = item.get("class") or item.get("class_name") or item.get("name") or "Object"
            if not isinstance(raw_class, str):
                raw_class = str(raw_class)

            raw_conf = item.get("confidence", item.get("score"))
            if raw_conf is None:
                continue
            try:
                confidence = float(raw_conf)
                if confidence <= 0.0:
                    continue
            except (ValueError, TypeError):
                continue

            track_id = item.get("track_id") or item.get("tracker_id")

            # Extract coordinates safely
            x1, y1, x2, y2 = 0, 0, 0, 0
            if "x" in item and "y" in item and "width" in item and "height" in item:
                cx, cy = float(item["x"]), float(item["y"])
                w, h = float(item["width"]), float(item["height"])

                if cx <= 1.0 and cy <= 1.0 and w <= 1.0 and h <= 1.0:
                    cx, cy = cx * frame_w, cy * frame_h
                    w, h = w * frame_w, h * frame_h

                x1 = int(max(0, cx - w / 2))
                y1 = int(max(0, cy - h / 2))
                x2 = int(min(frame_w, cx + w / 2))
                y2 = int(min(frame_h, cy + h / 2))
            elif "x_min" in item and "y_min" in item and "x_max" in item and "y_max" in item:
                x1 = int(float(item["x_min"]))
                y1 = int(float(item["y_min"]))
                x2 = int(float(item["x_max"]))
                y2 = int(float(item["y_max"]))
            elif "box" in item and isinstance(item["box"], (list, tuple)) and len(item["box"]) == 4:
                x1, y1, x2, y2 = [int(float(v)) for v in item["box"]]
            else:
                continue

            # Ensure coordinates stay within frame boundaries and are non-degenerate
            x1 = max(0, min(frame_w, x1))
            y1 = max(0, min(frame_h, y1))
            x2 = max(0, min(frame_w, x2))
            y2 = max(0, min(frame_h, y2))
            if x2 <= x1 or y2 <= y1:
                continue

            display_name, color = get_class_display_and_color(raw_class)

            detections.append({
                "class_name": display_name,
                "raw_class": raw_class,
                "confidence": confidence,
                "box": (x1, y1, x2, y2),
                "color": color,
                "track_id": track_id,
            })
        except Exception:
            # Skip malformed prediction entry without aborting stream
            continue

    return detections


# ---------------------------------------------------------------------------
# Backend Detection Ingestion Bridge (Phase 3)
# ---------------------------------------------------------------------------
def post_detection_to_backend(
    backend_url: str,
    decision: RuleDecision,
    frame: Optional[np.ndarray] = None,
    api_key: Optional[str] = None,
    timeout: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    POSTs verified detection events to the backend at /api/detections.
    Connects the ai-model detection pipeline to the backend database & dashboard.
    """
    if not backend_url or not decision or not decision.is_event:
        return None

    # Determine event type based on action / normalized class
    is_person = (
        decision.action == RuleAction.HUMAN_NOTIFICATION_REQUIRED
        or decision.class_name.lower() in ("human", "person")
    )
    event_type = "PERSON_DETECTED" if is_person else "ANIMAL_DETECTED"

    snapshot_b64 = None
    if frame is not None:
        try:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            import base64
            snapshot_b64 = base64.b64encode(buf).decode("utf-8")
        except Exception:
            snapshot_b64 = None

    payload = {
        "camera_id": decision.camera_id,
        "event_type": event_type,
        "confidence": round(float(decision.confidence), 4),
        "species": decision.class_name,
        "movement_direction": getattr(decision, "movement_direction", None),
        "boundary_crossing": (
            "boundary" in (decision.zone_name or "").lower()
            or "boundary" in (decision.zone_id or "").lower()
        ),
        "snapshot_base64": snapshot_b64,
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        import requests
        url = backend_url.rstrip("/") + "/api/detections"
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code in (200, 201):
            return resp.json()
        else:
            return {"status": resp.status_code, "detail": resp.text}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Asynchronous Inference Worker with Rule Engine Evaluation
# ---------------------------------------------------------------------------
class RoboflowWorker:
    """Runs Roboflow inference & Rule Engine evaluation in a background worker."""

    def __init__(
        self,
        client: Any,
        workspace: Optional[str],
        workflow: Optional[str],
        model_id: Optional[str],
        rule_engine: Optional[DetectionRuleEngine] = None,
        camera_id: str = "CAM-001",
        village_id: Optional[str] = "VIL-A",
        zone_override: Optional[str] = None,
        min_confidence: float = 0.60,
        inference_interval: float = 0.5,
        backend_url: Optional[str] = None,
        backend_api_key: Optional[str] = None,
    ):
        self.client = client
        self.workspace = workspace
        self.workflow = workflow
        self.model_id = model_id
        self.rule_engine = rule_engine or DetectionRuleEngine(default_confidence_threshold=min_confidence)
        self.camera_id = camera_id
        self.village_id = village_id
        self.zone_override = zone_override
        self.min_confidence = min_confidence
        self.inference_interval = inference_interval
        self.backend_url = backend_url
        self.backend_api_key = backend_api_key

        self._frame_lock = threading.Lock()
        self._pending_frame: Optional[np.ndarray] = None
        self._latest_detections: List[Dict[str, Any]] = []
        self._latest_decision: Optional[RuleDecision] = None
        self._last_inference_time = 0.0
        self._latency_ms = 0.0
        self._last_error: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._total_inferences = 0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def submit_frame(self, frame: np.ndarray):
        """Submit a new frame if sufficient time has elapsed (rate limiting)."""
        now = time.time()
        if now - self._last_inference_time < self.inference_interval:
            return

        with self._frame_lock:
            self._pending_frame = frame.copy()
            self._last_inference_time = now

    def get_results(self) -> Tuple[List[Dict[str, Any]], Optional[RuleDecision], float, Optional[str], int]:
        """Returns (latest_detections, latest_decision, latency_ms, last_error, total_inferences)."""
        with self._frame_lock:
            return (
                list(self._latest_detections),
                self._latest_decision,
                self._latency_ms,
                self._last_error,
                self._total_inferences,
            )

    def _run(self):
        while self._running:
            frame_to_process = None
            with self._frame_lock:
                if self._pending_frame is not None:
                    frame_to_process = self._pending_frame
                    self._pending_frame = None

            if frame_to_process is None:
                time.sleep(0.02)
                continue

            h, w = frame_to_process.shape[:2]
            t_start = time.time()
            try:
                # Mode 1: Roboflow Workflow execution
                if self.workspace and self.workflow:
                    raw_result = self.client.run_workflow(
                        workspace_name=self.workspace,
                        workflow_id=self.workflow,
                        images={"image": frame_to_process},
                    )
                # Mode 2: Direct Roboflow Model ID execution
                elif self.model_id:
                    raw_result = self.client.infer(
                        inference_input=frame_to_process,
                        model_id=self.model_id,
                    )
                else:
                    raise ValueError(
                        "Neither (ROBOFLOW_WORKSPACE & ROBOFLOW_WORKFLOW) nor ROBOFLOW_MODEL_ID was specified."
                    )

                latency = (time.time() - t_start) * 1000.0
                all_preds = extract_predictions(raw_result, frame_w=w, frame_h=h)

                processed_detections: List[Dict[str, Any]] = []
                last_decision: Optional[RuleDecision] = None

                # Process every detection through Phase 2 Detection Rule Engine
                for pred in all_preds:
                    decision = self.rule_engine.evaluate(
                        pred,
                        camera_id=self.camera_id,
                        village_id=self.village_id,
                        zone=self.zone_override if self.zone_override and self.zone_override != "auto" else None,
                        current_time=time.time(),
                    )
                    # Print formatted terminal output matching Module 9 specifications
                    print("\n" + decision.format_terminal() + "\n")
                    last_decision = decision

                    # Attach decision data to detection
                    pred_entry = dict(pred)
                    pred_entry["decision"] = decision
                    pred_entry["is_event"] = decision.is_event
                    processed_detections.append(pred_entry)

                    # Phase 3: Forward alert events to backend if configured
                    if self.backend_url and decision.is_event:
                        threading.Thread(
                            target=post_detection_to_backend,
                            kwargs={
                                "backend_url": self.backend_url,
                                "decision": decision,
                                "frame": frame_to_process,
                                "api_key": self.backend_api_key,
                            },
                            daemon=True,
                        ).start()

                with self._frame_lock:
                    if self._last_error is not None:
                        print(f"\n[INFERENCE RECOVERED] Connection restored. Inference resumed ({latency:.0f}ms).\n")
                    self._latest_detections = processed_detections
                    if last_decision is not None:
                        self._latest_decision = last_decision
                    self._latency_ms = latency
                    self._last_error = None
                    self._total_inferences += 1

            except Exception as err:
                latency = (time.time() - t_start) * 1000.0
                err_str = str(err)
                err_lower = err_str.lower()

                # User-friendly error classifications
                if any(k in err_lower for k in ["401", "unauthorized", "api_key", "api key", "forbidden", "authentication failed"]):
                    err_msg = "API Authentication error: Invalid or unauthorized ROBOFLOW_API_KEY (check credentials)"
                elif any(k in err_lower for k in ["timeout", "timed out", "connecttimeout", "readtimeout"]):
                    err_msg = f"Network Timeout: Inference request timed out ({err_str})"
                elif any(k in err_lower for k in ["404", "not found", "workflow not found", "model not found", "workspace not found"]):
                    err_msg = f"Model/Workflow Lookup error: Target Roboflow resource not found ({err_str})"
                elif any(k in err_lower for k in ["connection", "failed to establish a new connection", "name or service not known"]):
                    err_msg = f"Network Connection error: Unable to reach Roboflow API ({err_str})"
                else:
                    err_msg = f"Inference API Error: {err_str}"

                # Print to terminal ONLY when error state changes to prevent flooding
                if err_msg != self._last_error:
                    print(f"\n[INFERENCE ERROR] {err_msg}\n")

                with self._frame_lock:
                    self._last_error = err_msg
                    self._latency_ms = latency


# ---------------------------------------------------------------------------
# UI Overlay & Rendering
# ---------------------------------------------------------------------------
def draw_ui_overlay(
    frame: np.ndarray,
    detections: List[Dict[str, Any]],
    latest_decision: Optional[RuleDecision],
    fps: float,
    latency_ms: float,
    error: Optional[str],
    total_inferences: int,
    village_name: str = "Village A",
    camera_id: str = "CAM-001",
):
    """Renders modern bounding boxes, labels, risk indicators, and status telemetry on the frame."""
    h, w = frame.shape[:2]

    # Draw detected bounding boxes
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        color = det["color"]
        decision: Optional[RuleDecision] = det.get("decision")
        is_event = det.get("is_event", False)

        # Event status badge in label
        if is_event and decision:
            risk_badge = f"[{decision.risk_level}]" if decision.risk_level else ""
            status_tag = f"[{decision.action.value}] {risk_badge}".strip()
            box_thickness = 3
        else:
            status_tag = "[IGNORED]" if decision else ""
            box_thickness = 1

        label = f"{det['class_name']} {det['confidence'] * 100:.0f}% {status_tag}".strip()

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, box_thickness)

        # Label tag background
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.50
        thickness = 1
        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)

        tag_y1 = max(0, y1 - th - 8)
        tag_y2 = y1
        tag_x2 = min(w, x1 + tw + 10)

        cv2.rectangle(frame, (x1, tag_y1), (tag_x2, tag_y2), color, -1)
        cv2.putText(
            frame,
            label,
            (x1 + 5, tag_y2 - 5),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    # Top Status Banner (HUD)
    hud_height = 65
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_height), (20, 24, 33), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(
        frame,
        "WildShield AI | Phase 2 Rule Engine",
        (12, 22),
        font,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )

    location_info = f"Location: {village_name} | Camera: {camera_id} | FPS: {fps:.1f}"
    cv2.putText(frame, location_info, (12, 45), font, 0.42, (180, 210, 230), 1, cv2.LINE_AA)

    # Rule Engine Status / Action
    if latest_decision and latest_decision.is_event:
        if latest_decision.action == RuleAction.ANIMAL_ALERT_REQUIRED:
            risk_txt = f"[{latest_decision.risk_level or 'HIGH'}]"
            rule_status = f"ALERT {risk_txt}: {latest_decision.class_name} ({latest_decision.zone_name}) - Siren Active"
            rule_color = (0, 69, 255)  # Crimson Red
        else:
            rule_status = f"NOTIF: {latest_decision.class_name} ({latest_decision.zone_name}) - No Siren"
            rule_color = (0, 165, 255)  # Orange
    else:
        rule_status = f"Armed & Monitoring ({village_name})"
        rule_color = (0, 255, 127)  # Spring green

    cv2.putText(frame, rule_status, (w // 2 - 140, 24), font, 0.48, rule_color, 1, cv2.LINE_AA)

    # Telemetry and Key Controls
    if error:
        status_text = f"API Error: {error[:25]}..."
        status_color = (0, 0, 255)
    elif total_inferences == 0:
        status_text = "API: Connecting..."
        status_color = (0, 215, 255)
    else:
        status_text = f"API: {latency_ms:.0f}ms | {len(detections)} obj"
        status_color = (0, 255, 127)

    (stw, _), _ = cv2.getTextSize(status_text, font, 0.42, 1)
    cv2.putText(frame, status_text, (w - stw - 15, 22), font, 0.42, status_color, 1, cv2.LINE_AA)

    controls_hint = "Press 'S': Stop Siren | 'Q': Quit"
    (chw, _), _ = cv2.getTextSize(controls_hint, font, 0.42, 1)
    cv2.putText(frame, controls_hint, (w - chw - 15, 45), font, 0.42, (200, 220, 220), 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Roboflow YOLOv11 Webcam + Detection Rule Engine for WildShield AI"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Roboflow API Key (defaults to ROBOFLOW_API_KEY environment variable)",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Roboflow workspace name (defaults to ROBOFLOW_WORKSPACE env var)",
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default=None,
        help="Roboflow workflow ID (defaults to ROBOFLOW_WORKFLOW env var)",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default=None,
        help="Roboflow model ID if testing direct model endpoint (e.g. wildshield/1)",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Webcam device index (default: 0)",
    )
    parser.add_argument(
        "--village",
        type=str,
        default="Village A",
        help="Active demonstration village: 'Village A' (VIL-A) or 'Village B' (VIL-B)",
    )
    parser.add_argument(
        "--camera-id",
        type=str,
        default="CAM-001",
        help="Unique camera ID to assign to the webcam (default: CAM-001)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.60,
        help="Confidence score threshold for rule engine (default: 0.60 per Phase 2)",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=90.0,
        help="Alert cooldown duration in seconds (default: 90.0)",
    )
    parser.add_argument(
        "--human-cooldown",
        type=float,
        default=0.0,
        help="Human notification cooldown duration in seconds (default: 0.0, independent of animal siren cooldown)",
    )
    parser.add_argument(
        "--dup-window",
        type=float,
        default=10.0,
        help="Duplicate suppression window in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--zone",
        type=str,
        default="auto",
        help="Zone routing override (auto, forest, forest_boundary, agricultural, village_boundary, restricted)",
    )
    parser.add_argument(
        "--disable-siren",
        action="store_true",
        help="Disable acoustic siren playback on laptop speakers (silent mode)",
    )
    parser.add_argument(
        "--inference-fps",
        type=float,
        default=2.0,
        help="Target inference request rate in FPS to prevent rate-limits (default: 2.0)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="https://detect.roboflow.com",
        help="Roboflow API URL (default: https://detect.roboflow.com)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=os.environ.get("BACKEND_URL"),
        help="Backend URL to forward alerts to (e.g. http://localhost:8000), defaults to BACKEND_URL env var",
    )
    parser.add_argument(
        "--edge-api-key",
        type=str,
        default=os.environ.get("EDGE_API_KEY"),
        help="Optional edge API key for backend /api/detections ingestion",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional maximum number of frames to process before exiting (useful for automated testing)",
    )

    args = parser.parse_args()

    # 1. Resolve Credentials & Target Configuration
    api_key = args.api_key or os.environ.get("ROBOFLOW_API_KEY")
    workspace = args.workspace or os.environ.get("ROBOFLOW_WORKSPACE")
    workflow = args.workflow or os.environ.get("ROBOFLOW_WORKFLOW") or os.environ.get("ROBOFLOW_WORKFLOW_ID")
    model_id = args.model_id or os.environ.get("ROBOFLOW_MODEL_ID")

    print("\n" + "=" * 70)
    print("  WildShield AI - Phase 2: Roboflow Webcam & Detection Rule Engine")
    print("=" * 70)

    # 2. Initialize Subsystems (Village Manager, Siren Service, Rule Engine)
    village_manager = VillageManager()
    active_village = village_manager.get_village(args.village)
    if not active_village:
        print(f"[WARN] Village '{args.village}' not recognized. Falling back to Village A.")
        active_village = village_manager.get_village("VIL-A")

    # Associate webcam with selected village
    village_manager.switch_webcam_village(active_village.id)
    camera_cfg = village_manager.get_camera(args.camera_id)
    if not camera_cfg:
        camera_cfg = village_manager.assign_camera(
            camera_id=args.camera_id,
            village_id=active_village.id,
            zone_id=active_village.zone_ids[0] if active_village.zone_ids else "ZONE-A-FB",
        )

    siren_service = SirenService(
        default_cooldown_seconds=args.cooldown,
        dry_run=args.disable_siren,
    )

    rule_engine = DetectionRuleEngine(
        default_confidence_threshold=args.confidence,
        default_cooldown_seconds=args.cooldown,
        duplicate_window_seconds=args.dup_window,
        default_human_cooldown_seconds=args.human_cooldown,
        village_manager=village_manager,
        siren_service=siren_service,
        dry_run_audio=args.disable_siren,
    )

    siren_desc = active_village.siren_config.description if active_village.siren_config else "None"
    print(f"[*] Active Village    : {active_village.name} (ID: {active_village.id})")
    print(f"[*] Assigned Camera   : {camera_cfg.camera_id} ({camera_cfg.name})")
    print(f"[*] Siren Pattern     : {siren_desc}")
    print(f"[*] Laptop Sound Mode : {'DISABLED (Silent)' if args.disable_siren else 'ENABLED (Speaker Playback)'}")
    print(f"[*] Rule Threshold    : {args.confidence * 100:.0f}%")
    print(f"[*] Alert Cooldown    : {args.cooldown:.0f} seconds")
    print(f"[*] Dup Suppression   : {args.dup_window:.0f} seconds window")
    print(f"[*] Inference Rate    : At most {args.inference_fps} req/sec (rate-limit safe)")
    if args.backend:
        print(f"[*] Backend Relay     : ENABLED -> {args.backend}/api/detections")
    else:
        print("[*] Backend Relay     : DISABLED (Standalone mode)")

    # Validate Inference SDK Installation
    if InferenceHTTPClient is None:
        print("\n[ERROR] The 'inference-sdk' package is not installed.")
        print("Please install it by running:")
        print("    pip install inference-sdk opencv-python\n")
        sys.exit(1)

    # Validate API Key Presence
    if not api_key:
        print("\n[ERROR] Missing Roboflow API Key!")
        print("Please set your ROBOFLOW_API_KEY environment variable before running:")
        print("  In PowerShell:")
        print('    $env:ROBOFLOW_API_KEY="your_actual_roboflow_api_key"')
        print("  In CMD:")
        print("    set ROBOFLOW_API_KEY=your_actual_roboflow_api_key")
        print("  Or pass it as an argument: --api-key YOUR_KEY\n")
        sys.exit(1)

    # Verify Workflow or Model target configuration
    if not (workspace and workflow) and not model_id:
        print("\n[ERROR] Missing Roboflow Workflow / Model configuration!")
        print("You must supply either:")
        print("  1. Workflow: ROBOFLOW_WORKSPACE and ROBOFLOW_WORKFLOW environment variables")
        print("     (or --workspace <name> --workflow <id>)")
        print("  2. Model ID: ROBOFLOW_MODEL_ID environment variable (or --model-id <project/ver>)")
        print("\nExample (PowerShell):")
        print('  $env:ROBOFLOW_WORKSPACE="your-workspace"')
        print('  $env:ROBOFLOW_WORKFLOW="your-workflow-id"')
        print("  python ai-model/roboflow_webcam_test.py\n")
        sys.exit(1)

    masked_key = mask_api_key(api_key)
    print(f"[*] Roboflow API Key  : Configured ({masked_key})")
    if workspace and workflow:
        print(f"[*] Target Workflow   : Workspace '{workspace}' | Workflow '{workflow}'")
    if model_id:
        print(f"[*] Target Model ID   : {model_id}")

    # 3. Initialize Roboflow Inference Client
    try:
        client = InferenceHTTPClient(
            api_url=args.api_url,
            api_key=api_key,
        )
        if InferenceConfiguration is not None:
            try:
                client.configure(InferenceConfiguration(api_key_transport="both"))
            except Exception:
                pass
        print("[*] Inference Client  : Initialized successfully.")
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize InferenceHTTPClient: {e}")
        sys.exit(1)

    # 4. Access Webcam using OpenCV
    print(f"[*] Opening Webcam    : Device index {args.camera_index}...")
    cap = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"[WARN] CAP_DSHOW failed, falling back to default camera backend...")
        cap = cv2.VideoCapture(args.camera_index)

    if not cap.isOpened():
        print(f"\n[ERROR] Unable to access camera at index {args.camera_index}.")
        print("Troubleshooting for Windows:")
        print("  1. Ensure no other application (Zoom, Teams, Camera app) is using the webcam.")
        print("  2. Check Windows Camera Privacy Settings (Settings -> Privacy -> Camera).")
        print("  3. Try running with '--camera-index 1' if you have an external camera.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[+] Webcam Connected  : Resolution {actual_w}x{actual_h}")
    print("[*] Controls: 'S' = Manual Stop Siren | 'Q'/ESC = Quit\n")

    # 5. Start Background Inference Worker and Real-Time Capture
    worker = None
    window_name = f"WildShield AI - {active_village.name} ({camera_cfg.camera_id})"

    try:
        inference_interval = 1.0 / max(0.1, args.inference_fps)
        worker = RoboflowWorker(
            client=client,
            workspace=workspace,
            workflow=workflow,
            model_id=model_id,
            rule_engine=rule_engine,
            camera_id=camera_cfg.camera_id,
            village_id=active_village.id,
            zone_override=args.zone,
            min_confidence=args.confidence,
            inference_interval=inference_interval,
            backend_url=args.backend,
            backend_api_key=args.edge_api_key,
        )
        worker.start()

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 540)

        prev_time = time.time()
        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("\n[ERROR] Failed to read frame from webcam.")
                break

            frame_count += 1
            if args.max_frames and frame_count >= args.max_frames:
                print(f"\n[INFO] Reached maximum frame limit ({args.max_frames}). Exiting cleanly...")
                break

            now = time.time()
            fps = 1.0 / max(1e-5, now - prev_time)
            prev_time = now

            # Send frame to background worker
            worker.submit_frame(frame)

            # Retrieve latest detections, decisions, and worker state
            detections, latest_decision, latency_ms, last_error, total_infs = worker.get_results()

            # Render bounding boxes, labels, and telemetry
            display_frame = frame.copy()
            draw_ui_overlay(
                frame=display_frame,
                detections=detections,
                latest_decision=latest_decision,
                fps=fps,
                latency_ms=latency_ms,
                error=last_error,
                total_inferences=total_infs,
                village_name=active_village.name,
                camera_id=camera_cfg.camera_id,
            )

            cv2.imshow(window_name, display_frame)

            # 1. Check if user closed the window with 'X' button
            try:
                prop = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
                if prop < 1:
                    print("\n[INFO] Window closed by user ('X' clicked). Exiting cleanly...")
                    break
            except cv2.error:
                print("\n[INFO] Window destroyed. Exiting cleanly...")
                break
            except Exception:
                pass

            # 2. Key events: Q / ESC / S
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                print("\n[INFO] ESC pressed. Exiting cleanly...")
                break
            elif key in (ord("q"), ord("Q")):
                print("\n[INFO] 'Q' pressed. Exiting cleanly...")
                break
            elif key in (ord("s"), ord("S")):
                if rule_engine and hasattr(rule_engine, "siren_service"):
                    stop_res = rule_engine.siren_service.stop_siren()
                    print(f"\n[MANUAL CONTROL] {stop_res.message}\n")

    except KeyboardInterrupt:
        print("\n[INFO] KeyboardInterrupt received. Exiting...")
    finally:
        print("[*] Releasing resources...")
        if rule_engine and hasattr(rule_engine, "siren_service"):
            try:
                rule_engine.siren_service.stop_siren()
            except Exception as e:
                print(f"[WARN] Failed to stop siren: {e}")
        if worker:
            try:
                worker.stop()
            except Exception as e:
                print(f"[WARN] Failed to stop worker: {e}")
        if cap:
            try:
                cap.release()
            except Exception as e:
                print(f"[WARN] Failed to release webcam: {e}")
        try:
            cv2.destroyAllWindows()
        except Exception as e:
            print(f"[WARN] Failed to destroy OpenCV windows: {e}")
        print("[+] Test terminated cleanly.")


if __name__ == "__main__":
    main()
