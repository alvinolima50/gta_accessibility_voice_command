"""Detector de boca aberta/fechada.

Usa MAR (Mouth Aspect Ratio) = distância vertical lábios / distância horizontal.
Como a pessoa também fala (o que oscila MAR rapidamente), a decisão usa:
  - histerese (abre em OPEN_THRESHOLD, fecha em CLOSE_THRESHOLD)
  - tempo mínimo sustentado (HOLD_MS) antes de disparar callback

Assim, abrir a boca pra falar "atira" não abre a trava; manter aberta por
~200ms abre. Fechar a boca por ~100ms fecha.
"""

import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from gaze_tracker.core.tracker import (
    FaceFrame,
    LIP_CORNER_L,
    LIP_CORNER_R,
    LOWER_LIP_INNER,
    UPPER_LIP_INNER,
)


@dataclass
class MouthState:
    mar: float
    is_open: bool


class MouthDetector:
    def __init__(
        self,
        open_threshold: float = 0.35,
        close_threshold: float = 0.22,
        open_hold_ms: int = 200,
        close_hold_ms: int = 100,
    ) -> None:
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
        self.open_hold_ms = open_hold_ms
        self.close_hold_ms = close_hold_ms

        self._is_open = False
        self._pending_flip_at: Optional[float] = None
        self._pending_state: Optional[bool] = None
        self._last_mar = 0.0
        self._listener: Optional[Callable[[bool], None]] = None

    def set_listener(self, fn: Callable[[bool], None]) -> None:
        self._listener = fn

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def last_mar(self) -> float:
        return self._last_mar

    @staticmethod
    def compute_mar(face: FaceFrame) -> float:
        lm = face.landmarks
        if lm is None or lm.shape[0] < 478:
            return 0.0
        # Usa coordenadas normalizadas (já são proporcionais — razão é invariante à escala).
        up = lm[UPPER_LIP_INNER, :2]
        lo = lm[LOWER_LIP_INNER, :2]
        cl = lm[LIP_CORNER_L, :2]
        cr = lm[LIP_CORNER_R, :2]
        vertical   = float(np.linalg.norm(up - lo))
        horizontal = float(np.linalg.norm(cl - cr))
        if horizontal < 1e-6:
            return 0.0
        return vertical / horizontal

    def update(self, face: FaceFrame) -> MouthState:
        mar = self.compute_mar(face)
        self._last_mar = mar
        now = time.monotonic()

        # Determina o estado "bruto" do frame atual pela histerese
        if self._is_open:
            raw = mar > self.close_threshold  # só fecha quando cai bem
        else:
            raw = mar > self.open_threshold   # só abre quando sobe bem

        if raw != self._is_open:
            # Começou uma transição potencial — marca tempo
            if self._pending_state != raw:
                self._pending_state = raw
                self._pending_flip_at = now
            else:
                # Continuou pendendo pra trocar — cheque hold time
                hold = self.open_hold_ms if raw else self.close_hold_ms
                if self._pending_flip_at is not None and (now - self._pending_flip_at) * 1000 >= hold:
                    self._is_open = raw
                    self._pending_flip_at = None
                    self._pending_state = None
                    if self._listener:
                        try: self._listener(self._is_open)
                        except Exception as e:
                            print(f"[mouth] listener err: {e}", flush=True)
        else:
            # Frame atual confirma estado — limpa pending
            self._pending_flip_at = None
            self._pending_state = None

        return MouthState(mar=mar, is_open=self._is_open)
