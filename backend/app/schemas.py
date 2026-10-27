from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models import ZoneType, EventType, UserRole


# ---------- Zone ----------
class ZoneCreate(BaseModel):
    name: str
    type: ZoneType
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence_threshold: float = 0.6
    cooldown_seconds: int = 90
    siren_duration_seconds: int = 45


class ZoneOut(ZoneCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: Optional[str] = "safe"
    village: Optional[str] = None
    incidents: Optional[int] = 0


# ---------- Camera ----------
class CameraCreate(BaseModel):
    zone_id: str
    name: str
    stream_source: Optional[str] = None


class CameraOut(CameraCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_online: bool
    last_heartbeat: Optional[datetime] = None


class CameraHeartbeat(BaseModel):
    is_online: bool = True


# ---------- Detection event (posted by ai-model/inference.py) ----------
class DetectionEvent(BaseModel):
    camera_id: str
    event_type: EventType
    confidence: float
    snapshot_base64: Optional[str] = None  # optional inline image, else pre-uploaded path
    snapshot_path: Optional[str] = None
    species: Optional[str] = None              # e.g. "Elephant" — omit if model is class-agnostic
    movement_direction: Optional[str] = None    # e.g. "South-East" — needs a tracking step to fill
    boundary_crossing: bool = False


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    zone_id: str
    camera_id: str
    event_type: EventType
    confidence: float
    snapshot_path: Optional[str] = None
    siren_activated: bool
    sms_sent: bool
    species: Optional[str] = None
    movement_direction: Optional[str] = None
    boundary_crossing: bool
    risk_level: str
    status: str
    title: Optional[str] = None
    read: bool = False
    created_at: datetime


class AlertReadUpdate(BaseModel):
    read: Optional[bool] = None


# ---------- Contact ----------
class ContactCreate(BaseModel):
    name: str
    phone_number: str
    role: str = "authority"
    zone_ids: list[str] = []


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    phone_number: str
    role: str


# ---------- Auth & User Profile ----------
class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.OPERATOR


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    role: UserRole
    full_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    two_factor_enabled: bool = True
    last_login_at: Optional[datetime] = None
    created_at: datetime


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None


class SecuritySettingsOut(BaseModel):
    two_factor_enabled: bool
    authorized_devices_count: int = 1
    last_login: Optional[str] = None
    events: list[dict] = []


class HealthSummaryOut(BaseModel):
    cameras_online: int
    cameras_total: int
    cameras: str
    active_alerts: int
    sirens_on: int
    last_detection_time: Optional[str] = None

