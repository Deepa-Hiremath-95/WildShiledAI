"""
WildShield AI - Phase 2: Village-Specific Laptop Siren Service
==============================================================
Module 6:
Configurable laptop siren playback service for demonstration villages:
- Village A Pattern: "Three short beeps followed by one long beep"
- Village B Pattern: "Two long beeps followed by two short beeps"

Safety & Prototype Disclaimers:
- IMPORTANT: These are laptop prototype sounds played through local speakers.
  They do not claim to alert actual villagers or simulate field hardware.
- Physical siren hardware and SMS are NOT implemented in this phase.
- Human detections must NEVER activate the siren.
- Peacock detections must NEVER activate the siren.
- Village identity is derived strictly from camera configuration, not image classification.
- Duplicate and cooldown suppression prevents repeated acoustic triggers for ongoing incidents.
- Includes manual stop control.
"""

from dataclasses import dataclass
from enum import Enum
import math
import os
import struct
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import wave

from village_manager import SirenConfig, VillageConfig


# Windows audio library
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    winsound = None
    HAS_WINSOUND = False


class SirenStatus(str, Enum):
    PLAYED = "PLAYED"
    SUPPRESSED_COOLDOWN = "SUPPRESSED_COOLDOWN"
    SUPPRESSED_DUPLICATE = "SUPPRESSED_DUPLICATE"
    NOT_ACTIVATED_HUMAN = "NOT_ACTIVATED_HUMAN"
    NOT_ACTIVATED_PEACOCK = "NOT_ACTIVATED_PEACOCK"
    NOT_ACTIVATED = "NOT_ACTIVATED"
    MISSING_CONFIGURATION = "MISSING_CONFIGURATION"
    UNKNOWN_VILLAGE = "UNKNOWN_VILLAGE"
    STOPPED = "STOPPED"


@dataclass
class SirenPlaybackResult:
    """Outcome of siren trigger request."""
    status: SirenStatus
    village_id: Optional[str] = None
    village_name: Optional[str] = None
    pattern_name: Optional[str] = None
    pattern_description: Optional[str] = None
    audio_file: Optional[str] = None
    message: str = ""
    timestamp: float = 0.0

    @property
    def activated(self) -> bool:
        return self.status == SirenStatus.PLAYED


def synthesize_pattern_wav(
    file_path: str,
    beeps: List[Tuple[int, int]],
    pause_ms: int = 100,
    framerate: int = 44100,
    amplitude: int = 18000,
) -> str:
    """
    Synthesizes a PCM 16-bit Mono WAV file for a beep pattern using pure standard library.
    Each item in `beeps` is (frequency_hz, duration_ms).
    """
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    frames: List[bytes] = []

    for idx, (freq, dur_ms) in enumerate(beeps):
        # Generate tone samples
        num_samples = int(framerate * (dur_ms / 1000.0))
        for i in range(num_samples):
            val = int(amplitude * math.sin(2 * math.pi * freq * i / framerate))
            frames.append(struct.pack("<h", val))

        # Add pause if not last beep
        if idx < len(beeps) - 1 and pause_ms > 0:
            num_pause = int(framerate * (pause_ms / 1000.0))
            zero_byte = struct.pack("<h", 0)
            frames.extend([zero_byte] * num_pause)

    with wave.open(file_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b"".join(frames))

    return file_path


class SirenService:
    """
    Manages village-specific siren pattern selection, cooldown suppression,
    laptop speaker playback, and manual emergency stop.
    """

    def __init__(
        self,
        sounds_dir: Optional[str] = None,
        default_cooldown_seconds: float = 90.0,
        dry_run: bool = False,
    ):
        self.default_cooldown_seconds = default_cooldown_seconds
        self.dry_run = dry_run

        # Determine sound directory
        if sounds_dir:
            self.sounds_dir = os.path.abspath(sounds_dir)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.sounds_dir = os.path.join(base_dir, "sounds")

        os.makedirs(self.sounds_dir, exist_ok=True)

        # State tracking: village_id -> last_played_timestamp
        self._village_last_played: Dict[str, float] = {}
        # Track-level cooldowns: track_id -> last_siren_timestamp
        self._track_last_siren: Dict[Union[int, str], float] = {}

        self._active_playback = False
        self._playback_end_time = 0.0
        self._lock = threading.Lock()

        # Ensure demo sound files are pre-generated
        self._ensure_demo_sound_files()

    def reset_state(self):
        """Clears all cooldowns and stop states (useful in unit testing)."""
        with self._lock:
            self._village_last_played.clear()
            self._track_last_siren.clear()
            self._active_playback = False
            self._playback_end_time = 0.0

    @property
    def is_playing(self) -> bool:
        """Returns True if siren audio is actively playing through speakers."""
        with self._lock:
            if not self._active_playback:
                return False
            # Check if duration window has elapsed
            if self._playback_end_time > 0 and time.time() > self._playback_end_time:
                self._active_playback = False
                return False
            return True

    def _ensure_demo_sound_files(self):
        """Generates standard sound files for Village A and Village B if missing."""
        self.sound_a_path = os.path.join(self.sounds_dir, "village_a_siren.wav")
        self.sound_b_path = os.path.join(self.sounds_dir, "village_b_siren.wav")

        try:
            if not os.path.exists(self.sound_a_path):
                synthesize_pattern_wav(
                    self.sound_a_path,
                    beeps=[(900, 150), (900, 150), (900, 150), (900, 600)],
                    pause_ms=100,
                )

            if not os.path.exists(self.sound_b_path):
                synthesize_pattern_wav(
                    self.sound_b_path,
                    beeps=[(700, 500), (700, 500), (700, 150), (700, 150)],
                    pause_ms=150,
                )
        except Exception:
            # Non-critical if generation deferred
            pass

    def stop_siren(self) -> SirenPlaybackResult:
        """
        Manual stop control: Immediately ceases any ongoing siren sound playback.
        Uses SND_ASYNC with None, which instantaneously stops all asynchronous
        waveform playback in Windows WinMM without blocking.
        Repeated calls are safe and idempotent.
        """
        with self._lock:
            self._active_playback = False
            self._playback_end_time = 0.0
            if HAS_WINSOUND and not self.dry_run:
                try:
                    winsound.PlaySound(None, winsound.SND_ASYNC)
                except Exception:
                    pass

        return SirenPlaybackResult(
            status=SirenStatus.STOPPED,
            message="Manual stop command executed. Laptop siren stopped.",
            timestamp=time.time(),
        )

    def trigger_siren_for_village(
        self,
        village: Optional[VillageConfig],
        track_id: Optional[Union[int, str]] = None,
        current_time: Optional[float] = None,
        force: bool = False,
    ) -> SirenPlaybackResult:
        """
        Triggers laptop siren for the assigned village.
        Enforces cooldown and deduplication suppression unless force=True.
        """
        now = current_time if current_time is not None else time.time()

        # 1. Validate Village
        if village is None:
            return SirenPlaybackResult(
                status=SirenStatus.UNKNOWN_VILLAGE,
                message="Unknown village specified; siren skipped.",
                timestamp=now,
            )

        # 2. Validate Siren Configuration
        siren_cfg = village.siren_config
        if siren_cfg is None:
            return SirenPlaybackResult(
                status=SirenStatus.MISSING_CONFIGURATION,
                village_id=village.id,
                village_name=village.name,
                message=f"Village '{village.name}' has no configured siren sound pattern.",
                timestamp=now,
            )

        # 3. Check Cooldowns (unless force)
        cooldown = siren_cfg.cooldown_seconds if siren_cfg.cooldown_seconds is not None else self.default_cooldown_seconds
        last_played = self._village_last_played.get(village.id)

        if not force and last_played is not None:
            elapsed = now - last_played
            if elapsed < cooldown:
                remaining = int(math.ceil(cooldown - elapsed))
                return SirenPlaybackResult(
                    status=SirenStatus.SUPPRESSED_COOLDOWN,
                    village_id=village.id,
                    village_name=village.name,
                    pattern_name=siren_cfg.pattern_name,
                    pattern_description=siren_cfg.description,
                    message=f"Siren cooldown active for {village.name} ({remaining}s remaining).",
                    timestamp=now,
                )

        # 4. Check Track-Level Deduplication
        if not force and track_id is not None:
            last_track = self._track_last_siren.get(track_id)
            if last_track is not None and (now - last_track) < cooldown:
                return SirenPlaybackResult(
                    status=SirenStatus.SUPPRESSED_DUPLICATE,
                    village_id=village.id,
                    village_name=village.name,
                    pattern_name=siren_cfg.pattern_name,
                    pattern_description=siren_cfg.description,
                    message=f"Duplicate siren trigger suppressed for track ID {track_id}.",
                    timestamp=now,
                )

        # 5. Resolve Audio File Path
        audio_file = siren_cfg.audio_file_path
        if not audio_file or not os.path.exists(audio_file):
            if village.id.upper() in {"VIL-A", "VILLAGE-A", "VILLAGE_A"}:
                audio_file = self.sound_a_path
            elif village.id.upper() in {"VIL-B", "VILLAGE-B", "VILLAGE_B"}:
                audio_file = self.sound_b_path
            else:
                # Synthesize custom pattern file on the fly if needed
                custom_path = os.path.join(self.sounds_dir, f"{village.id.lower()}_siren.wav")
                try:
                    if not os.path.exists(custom_path) and siren_cfg.beeps:
                        synthesize_pattern_wav(
                            custom_path,
                            beeps=siren_cfg.beeps,
                            pause_ms=siren_cfg.pause_ms,
                        )
                    audio_file = custom_path
                except Exception:
                    audio_file = None

        # 6. Play Audio Asynchronously on Laptop Speakers
        total_duration_ms = 0
        if siren_cfg.beeps:
            total_duration_ms = sum(dur for _, dur in siren_cfg.beeps) + max(0, len(siren_cfg.beeps) - 1) * siren_cfg.pause_ms
        else:
            total_duration_ms = 2000

        with self._lock:
            self._village_last_played[village.id] = now
            if track_id is not None:
                self._track_last_siren[track_id] = now
            self._active_playback = True
            self._playback_end_time = now + (total_duration_ms / 1000.0)

        if HAS_WINSOUND and audio_file and os.path.exists(audio_file) and not self.dry_run:
            try:
                winsound.PlaySound(audio_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                pass  # Do not crash if sound card is busy or unavailable

        return SirenPlaybackResult(
            status=SirenStatus.PLAYED,
            village_id=village.id,
            village_name=village.name,
            pattern_name=siren_cfg.pattern_name,
            pattern_description=siren_cfg.description,
            audio_file=audio_file,
            message=f"{village.name} sound selected ({siren_cfg.description}).",
            timestamp=now,
        )

