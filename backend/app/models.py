import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id():
    return str(uuid.uuid4())


class ZoneType(str, enum.Enum):
    ANIMAL = "ANIMAL"
    RESTRICTED = "RESTRICTED"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"


class EventType(str, enum.Enum):
    ANIMAL_DETECTED = "ANIMAL_DETECTED"
    PERSON_DETECTED = "PERSON_DETECTED"


class Village(Base):
    __tablename__ = "villages"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False, unique=True)
    code = Column(String, nullable=True)  # e.g. "VIL-001"
    description = Column(String, nullable=True)
    siren_pattern = Column(String, default="pattern_1")  # pattern_1 (Village A), pattern_2 (Village B)
    emergency_contact = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zones = relationship("Zone", back_populates="village")
    cameras = relationship("Camera", back_populates="village")
    alerts = relationship("Alert", back_populates="village")
    detections = relationship("Detection", back_populates="village")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String, primary_key=True, default=gen_id)
    village_id = Column(String, ForeignKey("villages.id"), nullable=True)
    name = Column(String, nullable=False)
    type = Column(Enum(ZoneType), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    confidence_threshold = Column(Float, default=0.6)
    cooldown_seconds = Column(Integer, default=90)
    siren_duration_seconds = Column(Integer, default=45)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Current siren state for this zone — used by the /sirens compat endpoints and by
    # the dashboard's siren-control page. Updated both by auto-triggers (alert_engine)
    # and by manual operator activate/deactivate calls.
    siren_status = Column(Boolean, default=False)
    siren_activated_at = Column(DateTime, nullable=True)
    siren_reason = Column(String, default="No active threat")

    village = relationship("Village", back_populates="zones")
    cameras = relationship("Camera", back_populates="zone")
    alerts = relationship("Alert", back_populates="zone")
    detections = relationship("Detection", back_populates="zone")
    contacts = relationship("ZoneContact", back_populates="zone", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True, default=gen_id)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=False)
    village_id = Column(String, ForeignKey("villages.id"), nullable=True)
    name = Column(String, nullable=False)
    stream_source = Column(String, nullable=True)  # RTSP URL / device index
    is_online = Column(Boolean, default=False)
    last_heartbeat = Column(DateTime, nullable=True)
    last_alert_at = Column(DateTime, nullable=True)  # animal siren cooldown check
    last_human_alert_at = Column(DateTime, nullable=True)  # independent human notification cooldown
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zone = relationship("Zone", back_populates="cameras")
    village = relationship("Village", back_populates="cameras")
    alerts = relationship("Alert", back_populates="camera")
    detections = relationship("Detection", back_populates="camera")


class Detection(Base):
    """Historical record of all raw detections received from camera nodes."""
    __tablename__ = "detections"

    id = Column(String, primary_key=True, default=gen_id)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=False)
    village_id = Column(String, ForeignKey("villages.id"), nullable=True)
    event_type = Column(Enum(EventType), nullable=False)
    species = Column(String, nullable=True)
    confidence = Column(Float, nullable=False)
    movement_direction = Column(String, nullable=True)
    boundary_crossing = Column(Boolean, default=False)
    risk_level = Column(String, default="low")
    action_taken = Column(String, nullable=True)
    siren_triggered = Column(Boolean, default=False)
    snapshot_path = Column(String, nullable=True)
    alert_id = Column(String, ForeignKey("alerts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="detections")
    zone = relationship("Zone", back_populates="detections")
    village = relationship("Village", back_populates="detections")
    alert = relationship("Alert", back_populates="detection")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=gen_id)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=False)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    village_id = Column(String, ForeignKey("villages.id"), nullable=True)
    event_type = Column(Enum(EventType), nullable=False)
    confidence = Column(Float, nullable=False)
    snapshot_path = Column(String, nullable=True)
    siren_activated = Column(Boolean, default=False)
    sms_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    species = Column(String, nullable=True)
    movement_direction = Column(String, nullable=True)
    boundary_crossing = Column(Boolean, default=False)
    risk_level = Column(String, default="medium")  # low | medium | high | critical
    status = Column(String, default="active")  # active | resolved
    title = Column(String, nullable=True)
    read = Column(Boolean, default=False)

    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String, nullable=True)

    zone = relationship("Zone", back_populates="alerts")
    camera = relationship("Camera", back_populates="alerts")
    village = relationship("Village", back_populates="alerts")
    detection = relationship("Detection", back_populates="alert", uselist=False)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    role = Column(String, default="authority")

    zones = relationship("ZoneContact", back_populates="contact", cascade="all, delete-orphan")


class ZoneContact(Base):
    """Many-to-many: which contacts get notified for which zones."""
    __tablename__ = "zone_contacts"

    id = Column(String, primary_key=True, default=gen_id)
    zone_id = Column(String, ForeignKey("zones.id"), nullable=False)
    contact_id = Column(String, ForeignKey("contacts.id"), nullable=False)

    zone = relationship("Zone", back_populates="contacts")
    contact = relationship("Contact", back_populates="zones")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.OPERATOR)
    full_name = Column(String, default="Forest Officer")
    email = Column(String, default="officer@wildshield.ai")
    location = Column(String, default="Central Forest Command")
    two_factor_enabled = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemSetting(Base):
    """Persistent global and runtime system configurations."""
    __tablename__ = "system_settings"

    id = Column(String, primary_key=True, default=gen_id)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    """Immutable audit trail for operational decisions, status transitions, and actions."""
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, nullable=True)
    username = Column(String, nullable=True)
    action = Column(String, nullable=False)  # e.g. "ALERT_RESOLVED", "SIREN_ACTIVATED", "SIREN_HALTED"
    resource_type = Column(String, nullable=False)  # "alert", "siren", "camera", "village", "zone", "settings"
    resource_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        if "entity_type" in kwargs and "resource_type" not in kwargs:
            kwargs["resource_type"] = kwargs.pop("entity_type")
        if "entity_id" in kwargs and "resource_id" not in kwargs:
            kwargs["resource_id"] = kwargs.pop("entity_id")
        super().__init__(**kwargs)

    @property
    def entity_type(self):
        return self.resource_type

    @property
    def entity_id(self):
        return self.resource_id
