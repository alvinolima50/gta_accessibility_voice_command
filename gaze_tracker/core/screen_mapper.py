"""Mapeamento features → pixel da tela.

Usa polinômio de grau 2 com features cruzadas:
  Φ = [1, ix, iy, yaw, pitch, ix*iy, ix*yaw, iy*pitch, ix², iy², yaw², pitch²]

Dois modelos lineares independentes: um pra X, um pra Y.
Ajustados via mínimos quadrados (np.linalg.lstsq), com regularização leve
(ridge) implementada como soma de identidade.

Serializável em JSON (lista de coeficientes + dimensões da tela).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np


FEATURE_NAMES = [
    "1", "ix", "iy", "yaw", "pitch",
    "ix*iy", "ix*yaw", "iy*pitch",
    "ix^2", "iy^2", "yaw^2", "pitch^2",
]
NFEAT = len(FEATURE_NAMES)


def build_features(ix: float, iy: float, yaw: float, pitch: float) -> np.ndarray:
    return np.array([
        1.0,
        ix, iy, yaw, pitch,
        ix * iy, ix * yaw, iy * pitch,
        ix * ix, iy * iy, yaw * yaw, pitch * pitch,
    ], dtype=np.float64)


@dataclass
class Calibration:
    # Coeficientes para x e y: cada um shape (NFEAT,)
    coef_x: List[float]
    coef_y: List[float]
    screen_w: int
    screen_h: int
    n_samples: int

    def to_dict(self) -> dict:
        return {
            "coef_x": self.coef_x,
            "coef_y": self.coef_y,
            "screen_w": self.screen_w,
            "screen_h": self.screen_h,
            "n_samples": self.n_samples,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        return cls(
            coef_x=list(d["coef_x"]),
            coef_y=list(d["coef_y"]),
            screen_w=int(d["screen_w"]),
            screen_h=int(d["screen_h"]),
            n_samples=int(d.get("n_samples", 0)),
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> Optional["Calibration"]:
        path = Path(path)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except Exception as e:
            print(f"[calibration] falha ao carregar {path}: {e}", flush=True)
            return None


def fit(features: np.ndarray, targets_xy: np.ndarray,
        screen_w: int, screen_h: int, ridge: float = 1e-3) -> Calibration:
    """features: (N, NFEAT). targets_xy: (N, 2) em pixels."""
    assert features.shape[1] == NFEAT
    assert features.shape[0] == targets_xy.shape[0]
    A = features
    # Ridge: resolve (AᵀA + λI) β = Aᵀy
    AtA = A.T @ A + ridge * np.eye(NFEAT)
    Aty_x = A.T @ targets_xy[:, 0]
    Aty_y = A.T @ targets_xy[:, 1]
    coef_x = np.linalg.solve(AtA, Aty_x)
    coef_y = np.linalg.solve(AtA, Aty_y)
    return Calibration(
        coef_x=coef_x.tolist(),
        coef_y=coef_y.tolist(),
        screen_w=screen_w,
        screen_h=screen_h,
        n_samples=int(features.shape[0]),
    )


class ScreenMapper:
    def __init__(self, calibration: Optional[Calibration] = None) -> None:
        self._cal = calibration

    @property
    def calibration(self) -> Optional[Calibration]:
        return self._cal

    def set_calibration(self, cal: Calibration) -> None:
        self._cal = cal

    def is_ready(self) -> bool:
        return self._cal is not None

    def predict(self, ix: float, iy: float, yaw: float, pitch: float
                ) -> Optional[tuple[float, float]]:
        if self._cal is None:
            return None
        phi = build_features(ix, iy, yaw, pitch)
        cx = np.array(self._cal.coef_x)
        cy = np.array(self._cal.coef_y)
        x = float(phi @ cx)
        y = float(phi @ cy)
        # Clamp pro range da tela (evita cursor voar pra fora)
        x = float(np.clip(x, 0, self._cal.screen_w - 1))
        y = float(np.clip(y, 0, self._cal.screen_h - 1))
        return x, y
