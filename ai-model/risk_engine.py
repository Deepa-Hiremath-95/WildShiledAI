"""
WildShield AI - Phase 2: Risk Assessment Engine
===============================================
Module 5:
Separate risk assessment module evaluating:
- Detected species (Elephant, Leopard, Wild_boar, Deer, Human)
- Assigned monitoring zone (Forest Zone, Forest Boundary, Agricultural, Village Boundary, Restricted)
- Confidence score (numerical probability)
- Detection persistence across multiple frames (track-based or temporal window)
- Movement direction (evaluated ONLY when validated trajectory tracking is available)

Classification Levels:
- LOW
- MEDIUM
- HIGH

All rules are transparent, explainable, and configurable without ungrounded
claims of predicting animal intent or attacks.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class RiskAssessmentResult:
    """Outcome of risk assessment evaluation with explainable reasoning."""
    level: RiskLevel
    score: float  # Normalized score 0.0 to 1.0
    species: str
    zone_type: str
    confidence: float
    persistence_count: int
    movement_direction: Optional[str] = None
    reasoning: str = ""

    def __str__(self) -> str:
        return f"[{self.level.value}] (Score: {self.score:.2f}) - {self.reasoning}"


class RiskAssessmentEngine:
    """
    Evaluates risk based on species threat profile, zone sensitivity,
    confidence metrics, multi-frame persistence, and validated movement trajectory.
    """

    def __init__(self, persistence_window_seconds: float = 8.0):
        self.persistence_window_seconds = persistence_window_seconds
        # Tracks recent detection histories: track_id -> List of (timestamp, centroid_x, centroid_y)
        self._track_history: Dict[Union[int, str], List[Tuple[float, float, float]]] = {}
        # Class-level frame counts for non-tracked detections: (class_name, zone_id) -> List of timestamps
        self._detection_timestamps: Dict[Tuple[str, str], List[float]] = {}

    def reset_state(self):
        """Clears persistence and tracking histories."""
        self._track_history.clear()
        self._detection_timestamps.clear()

    def update_history(
        self,
        class_name: str,
        zone_id: str,
        box: Optional[Tuple[int, int, int, int]] = None,
        track_id: Optional[Union[int, str]] = None,
        timestamp: Optional[float] = None,
    ) -> Tuple[int, Optional[str]]:
        """
        Updates internal tracking buffer and returns (persistence_count, movement_direction).
        Movement direction is computed ONLY if at least 3 historical points are present.
        """
        now = timestamp if timestamp is not None else time.time()
        persistence_count = 1
        movement_direction: Optional[str] = None

        if track_id is not None:
            # Update track history
            history = self._track_history.setdefault(track_id, [])
            cx = (box[0] + box[2]) / 2.0 if box else 0.0
            cy = (box[1] + box[3]) / 2.0 if box else 0.0
            history.append((now, cx, cy))

            # Prune old track points
            cutoff = now - self.persistence_window_seconds
            self._track_history[track_id] = [pt for pt in history if pt[0] >= cutoff]
            persistence_count = len(self._track_history[track_id])

            # Calculate direction if at least 3 points exist and box is valid
            valid_pts = self._track_history[track_id]
            if len(valid_pts) >= 3 and box is not None:
                dx = valid_pts[-1][1] - valid_pts[0][1]
                dy = valid_pts[-1][2] - valid_pts[0][2]
                dist = math.hypot(dx, dy)
                if dist < 15.0:
                    movement_direction = "Stationary"
                elif dy > 20.0:  # Moving downward in camera frame (typically toward camera / boundary)
                    movement_direction = "Approaching village boundary"
                elif dy < -20.0:
                    movement_direction = "Moving away from village boundary"
                elif abs(dx) > 20.0:
                    movement_direction = "Lateral boundary movement"
                else:
                    movement_direction = "Indeterminate trajectory"
            else:
                movement_direction = None
        else:
            # Trackless persistence window based on class and zone
            key = (class_name.lower(), zone_id)
            timestamps = self._detection_timestamps.setdefault(key, [])
            timestamps.append(now)
            cutoff = now - self.persistence_window_seconds
            self._detection_timestamps[key] = [t for t in timestamps if t >= cutoff]
            persistence_count = len(self._detection_timestamps[key])
            movement_direction = None  # No tracking data available

        return persistence_count, movement_direction

    def assess_risk(
        self,
        species: str,
        zone_type: str,
        confidence: float,
        persistence_count: int = 1,
        movement_direction: Optional[str] = None,
        zone_name: Optional[str] = None,
    ) -> RiskAssessmentResult:
        """
        Assesses risk using transparent, configurable domain rules.
        """
        canonical = species.strip().lower()
        zone_str = zone_type.strip().lower()
        z_display = zone_name or zone_type

        # 1. Ignored or Excluded classes
        if canonical in {"peacock", "unknown", "unsupported"}:
            return RiskAssessmentResult(
                level=RiskLevel.LOW,
                score=0.10,
                species=species,
                zone_type=zone_type,
                confidence=confidence,
                persistence_count=persistence_count,
                movement_direction=movement_direction,
                reasoning=f"{species} is an excluded or non-threat class; evaluated as LOW risk.",
            )

        # 2. Human Detections
        if canonical in {"human", "person"}:
            if "restricted" in zone_str:
                return RiskAssessmentResult(
                    level=RiskLevel.MEDIUM,
                    score=0.65,
                    species="Human",
                    zone_type=zone_type,
                    confidence=confidence,
                    persistence_count=persistence_count,
                    movement_direction=movement_direction,
                    reasoning=f"Human activity in {z_display}; evaluated as MEDIUM risk for unauthorized presence (no siren).",
                )
            else:
                return RiskAssessmentResult(
                    level=RiskLevel.LOW,
                    score=0.20,
                    species="Human",
                    zone_type=zone_type,
                    confidence=confidence,
                    persistence_count=persistence_count,
                    movement_direction=movement_direction,
                    reasoning=f"Human presence in {z_display} is standard; evaluated as LOW risk.",
                )

        # 3. High-Threat Wildlife: Elephant and Leopard
        is_high_threat_animal = canonical in {"elephant", "leopard"}
        # 4. Moderate-Threat Wildlife: Wild Boar
        is_wild_boar = canonical in {"wild_boar", "wild boar", "wildboar"}
        # 5. Low-to-Moderate Threat Wildlife: Deer
        is_deer = canonical == "deer"

        # Determine Zone Sensitivity Category
        is_village_boundary = "village boundary" in zone_str or "village_boundary" in zone_str
        is_agricultural = "agricultural" in zone_str
        is_forest_boundary = "forest boundary" in zone_str or "forest_boundary" in zone_str or zone_str == "animal"
        is_forest = "forest zone" in zone_str or zone_str == "forest"
        is_restricted = "restricted" in zone_str

        # Direction Modifier (elevates if approaching settlement)
        approaching = movement_direction == "Approaching village boundary"

        # Evaluation Matrix
        if is_high_threat_animal:
            if is_village_boundary:
                # Immediate perimeter to homes -> HIGH risk
                level = RiskLevel.HIGH
                score = 0.95
                reason = f"High-threat wildlife ({species}) at {z_display} posing immediate settlement risk."
            elif is_agricultural:
                # Farmland perimeter -> HIGH risk if persistent or high confidence, else MEDIUM
                if persistence_count >= 2 or confidence >= 0.70 or approaching:
                    level = RiskLevel.HIGH
                    score = 0.90
                    reason = f"High-threat wildlife ({species}) in {z_display} with sustained presence."
                else:
                    level = RiskLevel.MEDIUM
                    score = 0.70
                    reason = f"High-threat wildlife ({species}) observed in {z_display}."
            elif is_forest_boundary:
                # Buffer perimeter -> HIGH if persistent or very high confidence, else MEDIUM
                if persistence_count >= 3 or confidence >= 0.85 or approaching:
                    level = RiskLevel.HIGH
                    score = 0.85
                    reason = f"High-threat wildlife ({species}) in {z_display} approaching boundary corridor."
                else:
                    level = RiskLevel.MEDIUM
                    score = 0.65
                    reason = f"High-threat wildlife ({species}) detected in buffer {z_display}."
            elif is_forest:
                # Forest habitat -> MEDIUM risk (natural presence)
                level = RiskLevel.MEDIUM
                score = 0.50
                reason = f"High-threat wildlife ({species}) in natural habitat ({z_display}); monitored presence."
            else:
                level = RiskLevel.MEDIUM
                score = 0.60
                reason = f"Wildlife ({species}) detected in {z_display}."

        elif is_wild_boar:
            if is_village_boundary:
                if persistence_count >= 2 or approaching:
                    level = RiskLevel.HIGH
                    score = 0.85
                    reason = f"Wild boar in {z_display} posing human-wildlife conflict and safety risk."
                else:
                    level = RiskLevel.MEDIUM
                    score = 0.65
                    reason = f"Wild boar detected near {z_display}."
            elif is_agricultural:
                if persistence_count >= 2:
                    level = RiskLevel.HIGH
                    score = 0.80
                    reason = f"Persistent Wild boar in {z_display} posing significant crop damage risk."
                else:
                    level = RiskLevel.MEDIUM
                    score = 0.60
                    reason = f"Wild boar detected in {z_display}."
            elif is_forest_boundary:
                level = RiskLevel.MEDIUM
                score = 0.50
                reason = f"Wild boar detected in buffer {z_display}."
            else:
                level = RiskLevel.LOW
                score = 0.35
                reason = f"Wild boar detected in {z_display}; natural foraging zone."

        elif is_deer:
            if is_village_boundary:
                level = RiskLevel.MEDIUM
                score = 0.55
                reason = f"Deer detected near {z_display}."
            elif is_agricultural:
                if persistence_count >= 3:
                    level = RiskLevel.MEDIUM
                    score = 0.50
                    reason = f"Deer in {z_display} with persistent crop grazing."
                else:
                    level = RiskLevel.LOW
                    score = 0.35
                    reason = f"Deer observed in {z_display}."
            else:
                level = RiskLevel.LOW
                score = 0.25
                reason = f"Deer detected in {z_display}; normal herbivore activity."

        else:
            # Fallback for other wildlife
            level = RiskLevel.LOW
            score = 0.30
            reason = f"Detection of {species} in {z_display}."

        # Document movement trajectory transparently
        if movement_direction:
            reason += f" Movement trajectory: {movement_direction}."
        else:
            reason += " Trajectory tracking: Not available."

        return RiskAssessmentResult(
            level=level,
            score=score,
            species=species,
            zone_type=zone_type,
            confidence=confidence,
            persistence_count=persistence_count,
            movement_direction=movement_direction,
            reasoning=reason,
        )

