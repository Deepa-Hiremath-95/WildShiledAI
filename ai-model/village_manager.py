"""
WildShield AI - Phase 2: Village Management & Camera-Zone Association
====================================================================
Modules 1, 2, and 4:
- Configurable Village Management (VillageConfig, EmergencyContact, SirenConfig)
- Camera & Zone Association (CameraConfig, CameraRegistry)
- Monitoring Zone Management (ZoneType, ZoneConfig)

Pre-configures two demonstration villages:
- Village A (Unique ID: VIL-A, Siren: 3 short beeps + 1 long beep)
- Village B (Unique ID: VIL-B, Siren: 2 long beeps + 2 short beeps)

Provides camera association where camera identity drives village and zone
association without guessing geographic coordinates from animal images.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Module 4: Zone Types and Definitions
# ---------------------------------------------------------------------------
class ZoneType(str, Enum):
    """
    Supported monitoring zone types according to Phase 2 specifications:
    - Forest Zone
    - Forest Boundary Zone
    - Agricultural Zone
    - Village Boundary Zone
    - Restricted Zone
    """
    FOREST_ZONE = "Forest Zone"
    FOREST_BOUNDARY_ZONE = "Forest Boundary Zone"
    AGRICULTURAL_ZONE = "Agricultural Zone"
    VILLAGE_BOUNDARY_ZONE = "Village Boundary Zone"
    RESTRICTED_ZONE = "Restricted Zone"

    # Backward compatibility aliases
    ANIMAL = "Forest Boundary Zone"
    RESTRICTED = "Restricted Zone"


@dataclass
class ZoneConfig:
    """Configurable monitoring zone definition."""
    id: str
    name: str
    zone_type: ZoneType
    village_id: Optional[str] = None
    confidence_threshold: float = 0.60
    cooldown_seconds: float = 90.0
    spatial_bounds: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2)
    description: Optional[str] = None
    human_cooldown_seconds: Optional[float] = 0.0


# ---------------------------------------------------------------------------
# Module 1: Village Management & Siren/Contact Definitions
# ---------------------------------------------------------------------------
@dataclass
class EmergencyContact:
    """Emergency contact for future alerting/SMS use."""
    contact_id: str
    name: str
    role: str
    phone: str
    email: Optional[str] = None
    priority: int = 1


@dataclass
class SirenConfig:
    """Village-specific siren sound pattern configuration."""
    pattern_name: str
    description: str
    beeps: List[Tuple[int, int]]  # List of (frequency_hz, duration_ms)
    pause_ms: int = 100
    audio_file_path: Optional[str] = None
    cooldown_seconds: float = 90.0


@dataclass
class VillageConfig:
    """Village entity containing cameras, zones, siren pattern, and contacts."""
    id: str
    name: str
    camera_ids: List[str] = field(default_factory=list)
    zone_ids: List[str] = field(default_factory=list)
    siren_config: Optional[SirenConfig] = None
    emergency_contacts: List[EmergencyContact] = field(default_factory=list)
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Module 2: Camera & Zone Association
# ---------------------------------------------------------------------------
@dataclass
class CameraConfig:
    """
    Every camera must have:
    - Unique camera ID.
    - Assigned village ID.
    - Assigned monitoring zone.
    - Camera status.
    """
    camera_id: str
    village_id: str
    zone_id: str
    status: str = "ONLINE"  # ONLINE, ACTIVE, OFFLINE, MAINTENANCE
    name: str = "Camera"
    stream_source: Optional[str] = None


# ---------------------------------------------------------------------------
# Village & Camera Manager Registry
# ---------------------------------------------------------------------------
class VillageManager:
    """
    Central manager for Villages, Cameras, and Monitoring Zones.
    Maintains demonstration setups for Village A and Village B.
    """

    def __init__(self):
        self.villages: Dict[str, VillageConfig] = {}
        self.cameras: Dict[str, CameraConfig] = {}
        self.zones: Dict[str, ZoneConfig] = {}
        self.active_camera_id: str = "CAM-001"
        self._initialize_demo_environment()

    def _initialize_demo_environment(self):
        """Sets up Demonstration Village A and Village B with zones and test cameras."""
        # 1. Sound Patterns
        siren_a = SirenConfig(
            pattern_name="VIL-A-PATTERN",
            description="Three short beeps followed by one long beep",
            beeps=[
                (900, 150),
                (900, 150),
                (900, 150),
                (900, 600),
            ],
            pause_ms=100,
            cooldown_seconds=90.0,
        )

        siren_b = SirenConfig(
            pattern_name="VIL-B-PATTERN",
            description="Two long beeps followed by two short beeps",
            beeps=[
                (700, 500),
                (700, 500),
                (700, 150),
                (700, 150),
            ],
            pause_ms=150,
            cooldown_seconds=90.0,
        )

        # 2. Zones for Village A
        zone_a_fb = ZoneConfig(
            id="ZONE-A-FB",
            name="Forest Boundary",
            zone_type=ZoneType.FOREST_BOUNDARY_ZONE,
            village_id="VIL-A",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Buffer zone between dense forest and agricultural land in Village A",
        )
        zone_a_ag = ZoneConfig(
            id="ZONE-A-AG",
            name="Agricultural Zone",
            zone_type=ZoneType.AGRICULTURAL_ZONE,
            village_id="VIL-A",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Farmland and crop perimeter of Village A",
        )
        zone_a_vb = ZoneConfig(
            id="ZONE-A-VB",
            name="Village Boundary",
            zone_type=ZoneType.VILLAGE_BOUNDARY_ZONE,
            village_id="VIL-A",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Direct residential perimeter for Village A",
        )
        zone_a_res = ZoneConfig(
            id="ZONE-A-RES",
            name="Restricted Zone",
            zone_type=ZoneType.RESTRICTED_ZONE,
            village_id="VIL-A",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Restricted forest outpost near Village A",
        )
        zone_a_fz = ZoneConfig(
            id="ZONE-A-FZ",
            name="Forest Zone",
            zone_type=ZoneType.FOREST_ZONE,
            village_id="VIL-A",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Deep forest habitat adjacent to Village A",
        )

        for z in [zone_a_fb, zone_a_ag, zone_a_vb, zone_a_res, zone_a_fz]:
            self.zones[z.id] = z

        # 3. Zones for Village B
        zone_b_fb = ZoneConfig(
            id="ZONE-B-FB",
            name="Forest Boundary",
            zone_type=ZoneType.FOREST_BOUNDARY_ZONE,
            village_id="VIL-B",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Forest edge in Village B",
        )
        zone_b_ag = ZoneConfig(
            id="ZONE-B-AG",
            name="Agricultural Zone",
            zone_type=ZoneType.AGRICULTURAL_ZONE,
            village_id="VIL-B",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Farmland adjacent to Village B",
        )
        zone_b_vb = ZoneConfig(
            id="ZONE-B-VB",
            name="Village Boundary",
            zone_type=ZoneType.VILLAGE_BOUNDARY_ZONE,
            village_id="VIL-B",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Perimeter of Village B settlements",
        )
        zone_b_res = ZoneConfig(
            id="ZONE-B-RES",
            name="Restricted Zone",
            zone_type=ZoneType.RESTRICTED_ZONE,
            village_id="VIL-B",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Restricted wildlife corridor in Village B",
        )
        zone_b_fz = ZoneConfig(
            id="ZONE-B-FZ",
            name="Forest Zone",
            zone_type=ZoneType.FOREST_ZONE,
            village_id="VIL-B",
            confidence_threshold=0.60,
            cooldown_seconds=90.0,
            description="Deep forest sanctuary adjacent to Village B",
        )

        for z in [zone_b_fb, zone_b_ag, zone_b_vb, zone_b_res, zone_b_fz]:
            self.zones[z.id] = z

        # 4. Emergency Contacts
        contacts_a = [
            EmergencyContact("EC-A1", "Village A Forest Range Officer", "Ranger", "+91-9876543210", priority=1),
            EmergencyContact("EC-A2", "Village A Quick Response Volunteer", "Volunteer", "+91-9876543211", priority=2),
        ]
        contacts_b = [
            EmergencyContact("EC-B1", "Village B Wildlife Watcher", "Officer", "+91-9876543220", priority=1),
            EmergencyContact("EC-B2", "Village B Head Warden", "Head", "+91-9876543221", priority=2),
        ]

        # 5. Demonstration Village A
        vil_a = VillageConfig(
            id="VIL-A",
            name="Village A",
            camera_ids=["CAM-001", "webcam-0"],
            zone_ids=[zone_a_fb.id, zone_a_ag.id, zone_a_vb.id, zone_a_res.id, zone_a_fz.id],
            siren_config=siren_a,
            emergency_contacts=contacts_a,
            description="Demonstration Village A - Forest buffer zone community",
        )
        self.villages[vil_a.id] = vil_a

        # 6. Demonstration Village B
        vil_b = VillageConfig(
            id="VIL-B",
            name="Village B",
            camera_ids=["CAM-002", "CAM-003"],
            zone_ids=[zone_b_fb.id, zone_b_ag.id, zone_b_vb.id, zone_b_res.id, zone_b_fz.id],
            siren_config=siren_b,
            emergency_contacts=contacts_b,
            description="Demonstration Village B - Highland agricultural fringe community",
        )
        self.villages[vil_b.id] = vil_b

        # 7. Registered Cameras
        cam_1 = CameraConfig(
            camera_id="CAM-001",
            village_id="VIL-A",
            zone_id="ZONE-A-FB",
            status="ONLINE",
            name="Laptop Webcam (Village A Test)",
        )
        cam_webcam0 = CameraConfig(
            camera_id="webcam-0",
            village_id="VIL-A",
            zone_id="ZONE-A-FB",
            status="ONLINE",
            name="Default Webcam Alias",
        )
        cam_2 = CameraConfig(
            camera_id="CAM-002",
            village_id="VIL-B",
            zone_id="ZONE-B-FB",
            status="ONLINE",
            name="Village B Perimeter Camera",
        )
        cam_3 = CameraConfig(
            camera_id="CAM-003",
            village_id="VIL-B",
            zone_id="ZONE-B-AG",
            status="ONLINE",
            name="Village B Agricultural Camera",
        )

        for c in [cam_1, cam_webcam0, cam_2, cam_3]:
            self.cameras[c.camera_id] = c

    # -----------------------------------------------------------------------
    # Access and Configuration Methods
    # -----------------------------------------------------------------------
    def get_village(self, village_id_or_name: str) -> Optional[VillageConfig]:
        """Resolves village by ID or name (case-insensitive)."""
        if not village_id_or_name:
            return None
        # Check by ID
        if village_id_or_name in self.villages:
            return self.villages[village_id_or_name]
        # Check normalized ID / name
        cleaned = village_id_or_name.strip().lower().replace("_", " ")
        for v in self.villages.values():
            if v.id.lower() == cleaned or v.id.lower() == village_id_or_name.strip().lower():
                return v
            if v.name.lower() == cleaned or v.name.lower() == village_id_or_name.strip().lower():
                return v
        return None

    def get_camera(self, camera_id: str) -> Optional[CameraConfig]:
        """Looks up registered camera by ID."""
        return self.cameras.get(camera_id)

    def get_zone(self, zone_id_or_name: str) -> Optional[ZoneConfig]:
        """Looks up registered zone by ID or name."""
        if not zone_id_or_name:
            return None
        if zone_id_or_name in self.zones:
            return self.zones[zone_id_or_name]
        cleaned = zone_id_or_name.strip().lower()
        for z in self.zones.values():
            if z.name.lower() == cleaned or z.id.lower() == cleaned:
                return z
        return None

    def register_village(self, village: VillageConfig):
        """Register or update a village configuration."""
        self.villages[village.id] = village

    def register_camera(self, camera: CameraConfig):
        """Register or update a camera configuration."""
        self.cameras[camera.camera_id] = camera
        # Ensure camera is listed under village
        vil = self.get_village(camera.village_id)
        if vil and camera.camera_id not in vil.camera_ids:
            vil.camera_ids.append(camera.camera_id)

    def register_zone(self, zone: ZoneConfig):
        """Register or update a monitoring zone."""
        self.zones[zone.id] = zone
        if zone.village_id:
            vil = self.get_village(zone.village_id)
            if vil and zone.id not in vil.zone_ids:
                vil.zone_ids.append(zone.id)

    def switch_webcam_village(self, village_id_or_name: str, zone_id: Optional[str] = None) -> bool:
        """
        Simple configuration setting to switch the prototype laptop webcam
        between Village A and Village B.
        """
        target_village = self.get_village(village_id_or_name)
        if not target_village:
            return False

        # Select zone in target village
        target_zone_id = zone_id
        if not target_zone_id or target_zone_id not in self.zones:
            # Default to first zone or Forest Boundary of target village
            for zid in target_village.zone_ids:
                z = self.zones.get(zid)
                if z and z.zone_type == ZoneType.FOREST_BOUNDARY_ZONE:
                    target_zone_id = zid
                    break
            if not target_zone_id and target_village.zone_ids:
                target_zone_id = target_village.zone_ids[0]

        # Update test cameras
        for cam_id in ["CAM-001", "webcam-0"]:
            if cam_id in self.cameras:
                self.cameras[cam_id].village_id = target_village.id
                if target_zone_id:
                    self.cameras[cam_id].zone_id = target_zone_id
            else:
                self.cameras[cam_id] = CameraConfig(
                    camera_id=cam_id,
                    village_id=target_village.id,
                    zone_id=target_zone_id or "ZONE-FB",
                    status="ONLINE",
                    name=f"Laptop Webcam ({target_village.name})",
                )

        return True

    def assign_camera(self, camera_id: str, village_id: str, zone_id: str, status: str = "ONLINE") -> CameraConfig:
        """Assign or reassign a camera to a specific village and monitoring zone."""
        cam = CameraConfig(
            camera_id=camera_id,
            village_id=village_id,
            zone_id=zone_id,
            status=status,
            name=f"Camera {camera_id}",
        )
        self.register_camera(cam)
        return cam

