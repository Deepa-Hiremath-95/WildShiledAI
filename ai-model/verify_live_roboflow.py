"""
WildShield AI - Task 1: Live Roboflow Inference Verifier
=========================================================
Checks the active environment for Roboflow credentials, connects to the
Roboflow Inference API, and reports the verified live inference status.

Rules:
- Never hardcode or print API credentials in plain text.
- Do not treat mocked predictions as live inference.
- Report honest status with explicit classification.
"""

import os
import sys
import numpy as np

# Ensure ai-model is in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from roboflow_webcam_test import (
    load_env_cascading,
    mask_api_key,
    extract_predictions,
)

try:
    from inference_sdk import InferenceHTTPClient
except ImportError:
    InferenceHTTPClient = None


def verify_live_roboflow():
    loaded_envs = load_env_cascading(_current_dir)
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    workspace = os.environ.get("ROBOFLOW_WORKSPACE")
    workflow = os.environ.get("ROBOFLOW_WORKFLOW") or os.environ.get("ROBOFLOW_WORKFLOW_ID")
    model_id = os.environ.get("ROBOFLOW_MODEL_ID")

    print("\n" + "=" * 65)
    print("  WildShield AI - Task 1: Live Roboflow Inference Verification")
    print("=" * 65)
    print(f"[*] Environment files loaded : {loaded_envs if loaded_envs else 'None'}")
    print(f"[*] API Key present          : {'YES (' + mask_api_key(api_key) + ')' if api_key else 'NO (NOT CONFIGURED)'}")
    print(f"[*] Workspace                : {workspace or 'NOT SET'}")
    print(f"[*] Workflow ID              : {workflow or 'NOT SET'}")
    print(f"[*] Model ID                 : {model_id or 'NOT SET'}")

    if not api_key:
        print("\n[RESULT] Status: NOT TESTED (Awaiting Live Roboflow Credentials)")
        print("  -> ROBOFLOW_API_KEY is not defined in the active environment.")
        print("  -> Live Roboflow API cloud calls cannot be made without active credentials.")
        print("  -> Per instructions: Mocked predictions are NOT counted as live inference.")
        print("=" * 65 + "\n")
        return {
            "status": "NOT TESTED",
            "reason": "Missing ROBOFLOW_API_KEY",
            "predictions_count": 0,
        }

    if not (workspace and workflow) and not model_id:
        print("\n[RESULT] Status: NOT TESTED (Awaiting Target Configuration)")
        print("  -> Target Roboflow workspace/workflow or model ID is not configured.")
        print("=" * 65 + "\n")
        return {
            "status": "NOT TESTED",
            "reason": "Missing workflow/model configuration",
            "predictions_count": 0,
        }

    if InferenceHTTPClient is None:
        print("\n[RESULT] Status: FAILED (Dependency Error)")
        print("  -> inference-sdk is not installed.")
        print("=" * 65 + "\n")
        return {
            "status": "FAILED",
            "reason": "inference-sdk missing",
            "predictions_count": 0,
        }

    print("\n[*] Dispatching live inference request to https://detect.roboflow.com...")
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    try:
        client = InferenceHTTPClient(
            api_url="https://detect.roboflow.com",
            api_key=api_key,
        )
        if workspace and workflow:
            result = client.run_workflow(
                workspace_name=workspace,
                workflow_id=workflow,
                images={"image": dummy_frame},
            )
        else:
            result = client.infer(
                inference_input=dummy_frame,
                model_id=model_id,
            )

        preds = extract_predictions(result, frame_w=640, frame_h=480)
        print(f"[+] Live response received! Raw keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        print(f"[+] Parsed predictions count : {len(preds)}")
        print("\n[RESULT] Status: LIVE VERIFIED")
        print("=" * 65 + "\n")
        return {
            "status": "LIVE VERIFIED",
            "reason": "Actual Roboflow API request succeeded and returned response",
            "predictions_count": len(preds),
        }

    except Exception as err:
        err_str = str(err)
        err_lower = err_str.lower()
        if any(k in err_lower for k in ["401", "unauthorized", "api_key", "forbidden"]):
            classified = "API Authentication error: Invalid or unauthorized ROBOFLOW_API_KEY"
        elif any(k in err_lower for k in ["404", "not found"]):
            classified = f"Model/Workflow Lookup error: Target Roboflow resource not found ({err_str})"
        elif any(k in err_lower for k in ["timeout", "timed out"]):
            classified = f"Network Timeout: Request timed out ({err_str})"
        else:
            classified = f"Network/API Error: {err_str}"

        print(f"\n[LIVE CALL FAILED] {classified}")
        print("\n[RESULT] Status: NOT TESTED (Awaiting Valid Live Credentials)")
        print("=" * 65 + "\n")
        return {
            "status": "NOT TESTED",
            "reason": classified,
            "predictions_count": 0,
        }


if __name__ == "__main__":
    verify_live_roboflow()

