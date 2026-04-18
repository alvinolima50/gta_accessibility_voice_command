"""API pública do gaze_tracker.

Uma classe: `GazeTracker`. Orquestra tracker + estimador + filtro + mapper +
mouth detector. Salva/lê calibração em ~/.gaze_tracker/calibration.json.
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from gaze_tracker.core.filters import OneEuroFilter2D
from gaze_tracker.core.gaze_estimator import compute_features
from gaze_tracker.core.mouth import MouthDetector
from gaze_tracker.core.screen_mapper import Calibration, ScreenMapper
from gaze_tracker.core.tracker import FaceFrame, FaceTracker


DEFAULT_CAL_PATH = Path.home() / ".gaze_tracker" / "calibration.json"


@dataclass
class GazePoint:
    x: float
    y: float
    confidence: float
    timestamp: float


class GazeTracker:
    def __init__(
        self,
        camera_index: int = 0,
        calibration_path: Optional[Path] = None,
        one_euro_min_cutoff: float = 1.0,
        one_euro_beta: float = 0.007,
    ) -> None:
        self._cal_path = Path(calibration_path or DEFAULT_CAL_PATH)
        self._tracker = FaceTracker(camera_index=camera_index)
        self._mapper = ScreenMapper(Calibration.load(self._cal_path))
        self._mouth = MouthDetector()
        self._filter = OneEuroFilter2D(
            min_cutoff=one_euro_min_cutoff, beta=one_euro_beta,
        )

        self._lock = threading.Lock()
        self._last_gaze: Optional[GazePoint] = None
        self._gaze_listener: Optional[Callable[[GazePoint], None]] = None

        # Ligação: cada frame capturado vai por aqui
        self._tracker.set_listener(self._on_frame)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._tracker.start()

    def stop(self) -> None:
        self._tracker.stop()

    def is_calibrated(self) -> bool:
        return self._mapper.is_ready()

    @property
    def screen_size(self) -> Optional[tuple[int, int]]:
        cal = self._mapper.calibration
        if cal is None:
            return None
        return cal.screen_w, cal.screen_h

    # ------------------------------------------------------------------
    # Calibração
    # ------------------------------------------------------------------
    def run_calibration(self, quick: bool = False) -> bool:
        """Roda calibração interativa. O tracker precisa estar rodando.
        Salva em ~/.gaze_tracker/calibration.json em caso de sucesso.
        """
        # Importa aqui pra evitar dep circular quando o usuário só quer leitura.
        from gaze_tracker.calibration.calibrator import run_calibration

        if not self._tracker._thread or not self._tracker._thread.is_alive():
            self._tracker.start()
            time.sleep(0.5)  # dá tempo da câmera abrir
        cal = run_calibration(self._tracker, quick=quick)
        if cal is None:
            return False
        cal.save(self._cal_path)
        self._mapper.set_calibration(cal)
        self._filter.reset()
        return True

    def forget_calibration(self) -> None:
        try:
            if self._cal_path.exists():
                self._cal_path.unlink()
        except Exception:
            pass
        self._mapper = ScreenMapper(None)

    # ------------------------------------------------------------------
    # Callbacks de alto nível
    # ------------------------------------------------------------------
    def set_gaze_listener(self, fn: Callable[[GazePoint], None]) -> None:
        self._gaze_listener = fn

    def set_mouth_callback(self, fn: Callable[[bool], None]) -> None:
        self._mouth.set_listener(fn)

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def get_gaze(self) -> Optional[GazePoint]:
        with self._lock:
            return self._last_gaze

    def get_mouth_is_open(self) -> bool:
        return self._mouth.is_open

    def get_fps(self) -> float:
        return self._tracker.fps()

    # ------------------------------------------------------------------
    # Loop interno (chamado pelo FaceTracker)
    # ------------------------------------------------------------------
    def _on_frame(self, frame: FaceFrame) -> None:
        # Mouth sempre é atualizado (serve como gatilho independente)
        self._mouth.update(frame)

        if not self._mapper.is_ready():
            return
        feats = compute_features(frame)
        if feats is None:
            return
        pred = self._mapper.predict(feats.iris_x, feats.iris_y, feats.yaw, feats.pitch)
        if pred is None:
            return
        x_raw, y_raw = pred
        x, y = self._filter(x_raw, y_raw, t=frame.timestamp)
        point = GazePoint(
            x=float(x), y=float(y),
            confidence=float(feats.confidence),
            timestamp=frame.timestamp,
        )
        with self._lock:
            self._last_gaze = point
        if self._gaze_listener:
            try: self._gaze_listener(point)
            except Exception as e:
                print(f"[gaze] listener err: {e}", flush=True)
