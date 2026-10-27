import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app import models
from app.config import settings
from app.routers.alerts import auto_turn_off_siren
from app.services.ws_manager import manager


def test_health_summary_endpoint(client, db_session):
    from datetime import datetime, timedelta

    # Give cam-1 a fresh heartbeat so it's counted as online under the 90 s rule
    cam1 = db_session.query(models.Camera).filter(models.Camera.id == "cam-1").first()
    cam1.last_heartbeat = datetime.utcnow() - timedelta(seconds=5)
    # Ensure there is an active alert and a zone with siren_status=True
    zone = db_session.query(models.Zone).filter(models.Zone.id == "zone-1").first()
    zone.siren_status = True
    db_session.commit()

    res = client.get("/api/health/summary")
    assert res.status_code == 200
    data = res.json()

    assert "cameras_online" in data
    assert "cameras_total" in data
    assert "active_alerts" in data
    assert "sirens_on" in data
    assert "last_detection_time" in data
    assert data["cameras_online"] >= 1
    assert data["sirens_on"] >= 1

    # Also test the root mount alias
    res_root = client.get("/health/summary")
    assert res_root.status_code == 200
    assert res_root.json()["sirens_on"] == data["sirens_on"]


def test_edge_api_key_auth_open_by_default(client):
    """When edge_api_key is empty (default), ingestion is open without auth."""
    original_key = settings.edge_api_key
    settings.edge_api_key = ""
    try:
        payload = {
            "camera_id": "cam-1",
            "event_type": "ANIMAL_DETECTED",
            "confidence": 0.85,
            "species": "Elephant",
        }
        res = client.post("/api/detections", json=payload)
        assert res.status_code == 200
    finally:
        settings.edge_api_key = original_key


def test_edge_api_key_auth_enforced_when_configured(client, auth_headers):
    """When edge_api_key is configured:
    - X-API-Key with matching key passes
    - X-API-Key with wrong key returns 401
    - No X-API-Key and no Bearer token returns 401
    - Bearer token (logged in user via get_current_user) passes
    """
    original_key = settings.edge_api_key
    settings.edge_api_key = "secure-test-edge-key-999"
    payload = {
        "camera_id": "cam-1",
        "event_type": "ANIMAL_DETECTED",
        "confidence": 0.85,
        "species": "Elephant",
    }
    try:
        # 1. Valid API key header -> 200
        res_valid_key = client.post(
            "/api/detections", json=payload, headers={"X-API-Key": "secure-test-edge-key-999"}
        )
        assert res_valid_key.status_code == 200

        # 2. Invalid API key header -> 401
        res_bad_key = client.post(
            "/api/detections", json=payload, headers={"X-API-Key": "wrong-key"}
        )
        assert res_bad_key.status_code == 401
        assert "Invalid API key" in res_bad_key.json()["detail"]

        # 3. Missing both API key and user token -> 401
        res_no_auth = client.post("/api/detections", json=payload)
        assert res_no_auth.status_code == 401

        # 4. Valid User Bearer token (fallback via get_current_user) -> 200
        res_user_auth = client.post("/api/detections", json=payload, headers=auth_headers)
        assert res_user_auth.status_code == 200
    finally:
        settings.edge_api_key = original_key


@pytest.mark.anyio
async def test_siren_auto_turn_off_task(client, db_session):
    """auto_turn_off_siren background task sets Zone.siren_status=False after delay
    and broadcasts 'siren_off' via WebSocket."""
    zone = db_session.query(models.Zone).filter(models.Zone.id == "zone-2").first()
    zone.siren_status = True
    db_session.commit()

    with patch.object(manager, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        # Run auto_turn_off_siren with a tiny duration for test speed
        await auto_turn_off_siren("zone-2", duration=0.02, db=db_session)

        # Refresh zone from database
        db_session.expire_all()
        refreshed_zone = db_session.query(models.Zone).filter(models.Zone.id == "zone-2").first()
        assert refreshed_zone.siren_status is False

        # Verify broadcast
        mock_broadcast.assert_awaited_once()
        args = mock_broadcast.await_args[0]
        assert args[0] == "siren_off"
        assert args[1]["zone_id"] == "zone-2"
        assert args[1]["siren_status"] is False



def test_inference_script_api_key_handling():
    """Verify that inference.py defines --api-key argument and attaches X-API-Key header.
    Also verifies the new tracking kwargs (track_id, movement_direction, boundary_crossing)."""
    import os
    import sys
    from unittest.mock import patch, MagicMock
    import importlib.util

    mock_cv2 = MagicMock()
    mock_ultralytics = MagicMock()
    with patch.dict(sys.modules, {"cv2": mock_cv2, "ultralytics": mock_ultralytics}):
        inference_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "ai-model", "inference.py")
        )
        spec = importlib.util.spec_from_file_location(
            "inference",
            inference_path
        )
        inference_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inference_mod)

        # Reset anti-spam state so this test track is always fresh
        inference_mod._LAST_SENT.clear()

        # Test send_detection sends X-API-Key header when provided
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "alert-1"})
            fake_frame = MagicMock()
            with patch.object(inference_mod, "encode_snapshot", return_value="base64str"):
                inference_mod.send_detection(
                    backend="http://localhost:8000",
                    camera_id="cam-1",
                    track_id=42,
                    class_name="elephant",
                    confidence=0.9,
                    frame=fake_frame,
                    min_confidence_to_report=0.5,
                    movement_direction="NE",
                    boundary_crossing=False,
                    api_key="my-edge-key-test",
                )
                mock_post.assert_called_once()
                called_kwargs = mock_post.call_args[1]
                assert called_kwargs["headers"] == {"X-API-Key": "my-edge-key-test"}
                sent_payload = called_kwargs["json"]
                assert sent_payload["movement_direction"] == "NE"
                assert sent_payload["boundary_crossing"] is False


# ---------------------------------------------------------------------------
# Camera offline-after-90s (computed on read)
# ---------------------------------------------------------------------------

def test_camera_computed_offline_after_90s(client, db_session):
    """A camera whose last_heartbeat is > 90 s old should appear is_online=False
    in GET /api/cameras, even if the DB row still has is_online=True."""
    from datetime import datetime, timedelta

    cam = db_session.query(models.Camera).filter(models.Camera.id == "cam-1").first()
    cam.is_online = True
    cam.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
    db_session.commit()

    res = client.get("/api/cameras")
    assert res.status_code == 200
    cam_data = next((c for c in res.json() if c["id"] == "cam-1"), None)
    assert cam_data is not None
    assert cam_data["is_online"] is False, "Camera with stale heartbeat should be offline"


def test_camera_computed_online_with_fresh_heartbeat(client, db_session):
    """A camera with a recent heartbeat should appear is_online=True regardless of DB value."""
    from datetime import datetime, timedelta

    cam = db_session.query(models.Camera).filter(models.Camera.id == "cam-1").first()
    cam.is_online = False
    cam.last_heartbeat = datetime.utcnow() - timedelta(seconds=10)
    db_session.commit()

    res = client.get("/api/cameras")
    assert res.status_code == 200
    cam_data = next((c for c in res.json() if c["id"] == "cam-1"), None)
    assert cam_data is not None
    assert cam_data["is_online"] is True, "Camera with fresh heartbeat should be online"


def test_health_summary_reflects_offline_threshold(client, db_session):
    """GET /api/health/summary cameras_online must count only cameras with
    heartbeat within last 90 s; stale cameras must not count as online."""
    from datetime import datetime, timedelta

    cam1 = db_session.query(models.Camera).filter(models.Camera.id == "cam-1").first()
    cam1.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
    cam1.is_online = True  # DB says on, compute_camera_online returns False

    cam2 = db_session.query(models.Camera).filter(models.Camera.id == "cam-2").first()
    cam2.last_heartbeat = datetime.utcnow() - timedelta(seconds=5)
    cam2.is_online = True
    db_session.commit()

    res = client.get("/api/health/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["cameras_online"] == 1
    assert data["cameras_total"] == 2
    assert data["cameras"] == "1/2"
