from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field

from app.models import ZoneType, EventType, UserRole


# ---------- Village ----------
class VillageCreate(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    siren_pattern: Optional[str] = "pattern_1"
    emergency_contact: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool = True


class VillageUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    siren_pattern: Optional[str] = None
    emergency_contact: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None


class VillageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    siren_pattern: str = "pattern_1"
    emergency_contact: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    is_active: bool = True
    status: str = "safe"  # safe | at-risk
    zone: Optional[str] = None
    sirenId: Optional[str] = None
    sirenStatus: str = "off"
    cameras_count: int = 0
    zones_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


# ---------- Zone ----------
class ZoneCreate(BaseModel):
    name: str
    type: ZoneType
    village_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence_threshold: float = 0.6
    cooldown_seconds: int = 90
    siren_duration_seconds: int = 45


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[ZoneType] = None
    village_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence_threshold: Optional[float] = None
    cooldown_seconds: Optional[int] = None
    siren_duration_seconds: Optional[int] = None


class ZoneOut(ZoneCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: Optional[str] = "safe"
    village: Optional[str] = None
    incidents: Optional[int] = 0


# ---------- Camera ----------
class CameraCreate(BaseModel):
    zone_id: str
    name: str
    village_id: Optional[str] = None
    stream_source: Optional[str] = None
    stream_url: Optional[str] = None  # alias for stream_source


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    zone_id: Optional[str] = None
    village_id: Optional[str] = None
    stream_source: Optional[str] = None
    stream_url: Optional[str] = None


class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    zone_id: str
    village_id: Optional[str] = None
    name: str
    stream_source: Optional[str] = None
    is_online: bool = False
    last_heartbeat: Optional[datetime] = None
    last_alert_at: Optional[datetime] = None
    last_human_alert_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    village: Optional[str] = None
    zone: Optional[str] = None


class CameraHeartbeat(BaseModel):
    is_online: bool = True


# ---------- Detection event & Detection record ----------
class DetectionEvent(BaseModel):
    camera_id: str
    event_type: EventType
    confidence: float
    snapshot_base64: Optional[str] = None  # optional inline image, else pre-uploaded path
    snapshot_path: Optional[str] = None
    species: Optional[str] = None              # e.g. "Elephant", "Human"
    movement_direction: Optional[str] = None    # e.g. "South-East"
    boundary_crossing: bool = False


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    camera_id: str
    zone_id: str
    village_id: Optional[str] = None
    event_type: EventType
    species: Optional[str] = None
    confidence: float
    movement_direction: Optional[str] = None
    boundary_crossing: bool = False
    risk_level: str = "low"
    action_taken: Optional[str] = None
    siren_triggered: bool = False
    snapshot_path: Optional[str] = None
    alert_id: Optional[str] = None
    created_at: datetime
    location: Optional[str] = None
    affectedVillage: Optional[str] = None
    type: Optional[str] = None
    timestamp: Optional[str] = None
    sirenStatus: Optional[str] = "off"
    classification: Optional[str] = None
    imageLabel: Optional[str] = "No image captured"
    snapshotUrl: Optional[str] = None


# ---------- Alert ----------
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    zone_id: str
    camera_id: str
    village_id: Optional[str] = None
    event_type: EventType
    confidence: float
    snapshot_path: Optional[str] = None
    siren_activated: bool
    sms_sent: bool
    species: Optional[str] = None
    movement_direction: Optional[str] = None
    boundary_crossing: bool = False
    risk_level: str = "medium"
    status: str = "active"
    title: Optional[str] = None
    read: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AlertReadUpdate(BaseModel):
    read: Optional[bool] = None


class AlertResolveUpdate(BaseModel):
    notes: Optional[str] = None


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
    full_name: Optional[str] = "Operator"
    email: Optional[str] = None
    location: Optional[str] = None


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


# ---------- System Settings ----------
class SystemSettingsOut(BaseModel):
    min_confidence: float = 0.60
    animal_siren_cooldown_seconds: int = 90
    human_notification_cooldown_seconds: int = 10
    duplicate_detection_window_seconds: int = 10
    siren_duration_seconds: int = 45
    excluded_species: list[str] = ["peacock"]
    monitoring_preferences: dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class SystemSettingsUpdate(BaseModel):
    min_confidence: Optional[float] = None
    animal_siren_cooldown_seconds: Optional[int] = None
    human_notification_cooldown_seconds: Optional[int] = None
    duplicate_detection_window_seconds: Optional[int] = None
    siren_duration_seconds: Optional[int] = None
    excluded_species: Optional[list[str]] = None
    monitoring_preferences: Optional[dict[str, Any]] = None


# ---------- Audit Log ----------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
