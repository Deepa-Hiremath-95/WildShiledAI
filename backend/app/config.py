from typing import Union
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./wildshield.db"

    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 480

    sms_provider: str = "mock"  # mock | twilio | gsm_module
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # Roboflow
    roboflow_api_key: str = ""
    roboflow_workspace: str = ""
    roboflow_workflow: str = ""

    default_confidence_threshold: float = 0.6
    default_cooldown_seconds: int = 90
    default_siren_duration_seconds: int = 45

    environment: str = "development"  # development | production | testing
    enforce_ws_auth: bool = False     # require authentication for WebSocket connections
    edge_api_key: str = ""  # optional API key for edge device /api/detections ingestion (default empty = open)

    cors_origins: Union[list[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "*",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                import json
                try:
                    return json.loads(v_stripped)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    class Config:
        env_file = ".env"



settings = Settings()