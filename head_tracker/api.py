"""API pública do head_tracker.

HeadTracker entrega `HeadDirection` com:
  x, y    — normalizados em [-1, +1] usando a calibração pessoal.
             x=+1 = cabeça totalmente pra DIREITA (do usuário).
             y=+1 = cabeça totalmente pra BAIXO.
             Ou seja: 'olha pra direita → x positivo → mouse pra direita'.
             O sinal é sempre o intuitivo — a calibração cuida das convenções
             da webcam.
  dyaw_deg, dpitch_deg — delta cru em graus (útil pra debug).

Reusa do gaze_tracker: FaceTracker, MouthDetector, OneEuroFilter.
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from gaze_tracker.core.filters import OneEuroFilter
from gaze_tracker.core.mouth import MouthDetector
from gaze_tracker.core.tracker import FaceFrame, FaceTracker

from head_tracker.calibration import (
    DEFAULT_PROFILE_PATH,
    CalibrationProfile,
    run_calibration,
)
from head_tracker.estimator import estimate_head_pose


@dataclass
class HeadDirection:
    x: float             # [-1, +1] — +1 = cabeça pra direita (intuitivo)
    y: float             # [-1, +1] — +1 = cabeça pra baixo
    dyaw_deg: float      # delta cru em graus (pra debug)
    dpitch_deg: float
    droll_deg: float
    confidence: float
    timestamp: float


class HeadTracker:
    def __init__(
        self,
        camera_index: int = 0,
        profile_path: Optional[Path] = None,
        one_euro_min_cutoff: float = 1.2,
        one_euro_beta: float = 0.01,
    ) -> None:
        self._profile_path = Path(profile_path or DEFAULT_PROFILE_PATH)
        self._tracker = FaceTracker(camera_index=camera_index)
        self._mouth = MouthDetector()
        self._profile: Optional[CalibrationProfile] = CalibrationProfile.load(self._profile_path)

        # Suaviza os DELTAS brutos (em graus) antes de normalizar. Jitter some,
        # resposta permanece rápida em movimento.
        self._f_yaw   = OneEuroFilter(one_euro_min_cutoff, one_euro_beta)
        self._f_pitch = OneEuroFilter(one_euro_min_cutoff, one_euro_beta)
        self._f_roll  = OneEuroFilter(one_euro_min_cutoff, one_euro_beta)

        self._lock = threading.Lock()
        self._last_dir: Optional[HeadDirection] = None
        self._listener: Optional[Callable[[HeadDirection], None]] = None

        self._tracker.set_listener(self._on_frame)

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._tracker.start()

    def stop(self) -> None:
        self._tracker.stop()

    def has_profile(self) -> bool:
        return self._profile is not None

    @property
    def profile(self) -> Optional[CalibrationProfile]:
        return self._profile

    # ------------------------------------------------------------------
    def run_calibration(self) -> bool:
        """Calibração completa de 5 poses. Bloqueia até acabar."""
        if not self._tracker._thread or not self._tracker._thread.is_alive():
            self._tracker.start()
            time.sleep(0.5)
        profile = run_calibration(self._tracker)
        if profile is None:
            return False
        profile.save(self._profile_path)
        self._profile = profile
        self._f_yaw.reset()
        self._f_pitch.reset()
        self._f_roll.reset()
        return True

    def forget_calibration(self) -> None:
        try:
            if self._profile_path.exists():
                self._profile_path.unlink()
        except Exception:
            pass
        self._profile = None

    # Mantém o nome antigo como alias pra compat — aponta pra calibração nova.
    def capture_neutral(self) -> bool:
        return self.run_calibration()

    # ------------------------------------------------------------------
    def set_listener(self, fn: Callable[[HeadDirection], None]) -> None:
        self._listener = fn

    def set_mouth_callback(self, fn: Callable[[bool], None]) -> None:
        self._mouth.set_listener(fn)

    def get_direction(self) -> Optional[HeadDirection]:
        with self._lock:
            return self._last_dir

    def get_mouth_is_open(self) -> bool:
        return self._mouth.is_open

    def get_fps(self) -> float:
        return self._tracker.fps()

    # ------------------------------------------------------------------
    def _on_frame(self, frame: FaceFrame) -> None:
        self._mouth.update(frame)

        if self._profile is None:
            return
        pose = estimate_head_pose(frame)
        if pose is None:
            return

        # Deltas crus
        dyaw_raw   = pose.yaw_deg   - self._profile.neutral_yaw
        dpitch_raw = pose.pitch_deg - self._profile.neutral_pitch
        droll_raw  = pose.roll_deg

        # Suaviza em graus
        dyaw   = self._f_yaw(dyaw_raw,     t=frame.timestamp)
        dpitch = self._f_pitch(dpitch_raw, t=frame.timestamp)
        droll  = self._f_roll(droll_raw,   t=frame.timestamp)

        # Normaliza usando o perfil. Passamos o yaw/pitch absolutos filtrados
        # (neutro + delta suavizado).
        x, y = self._profile.normalize(
            self._profile.neutral_yaw   + dyaw,
            self._profile.neutral_pitch + dpitch,
        )

        direction = HeadDirection(
            x=x, y=y,
            dyaw_deg=float(dyaw),
            dpitch_deg=float(dpitch),
            droll_deg=float(droll),
            confidence=float(pose.confidence),
            timestamp=frame.timestamp,
        )
        with self._lock:
            self._last_dir = direction
        if self._listener:
            try: self._listener(direction)
            except Exception as e:
                print(f"[head] listener err: {e}", flush=True)
