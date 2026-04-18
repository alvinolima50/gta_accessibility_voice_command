"""Calibração do head tracker — 5 poses.

Aprende 2 coisas de uma vez:
  1. Pose NEUTRA (o "zero" pra cada eixo).
  2. EXTREMOS do range confortável do usuário em cada direção (direita, esquerda,
     cima, baixo). Com isso determinamos o SINAL (qual polaridade de yaw/pitch
     corresponde a "cabeça pra direita / cima" nesta webcam) e a MAGNITUDE
     (o range pessoal do pescoço).

Resultado: ao usar o tracker, convertemos (yaw, pitch) atuais em (x, y)
normalizados em [-1, 1] de forma natural: x=+1 significa "cabeça totalmente na
direita", independente de qual sinal de yaw representa isso na sua webcam.

Salva em ~/.head_tracker/profile.json.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from gaze_tracker.calibration.overlay import CalibrationOverlay
from gaze_tracker.core.tracker import FaceTracker
from head_tracker.estimator import HeadPose, estimate_head_pose


DEFAULT_PROFILE_PATH = Path.home() / ".head_tracker" / "profile.json"


@dataclass
class CalibrationProfile:
    """Perfil calibrado do usuário.

    Armazena a pose neutra e os ângulos nos 4 extremos. Na hora de usar, o
    tracker projeta (yaw, pitch) atuais nesses extremos pra dar uma direção
    normalizada em [-1, +1], com o sinal correto independente de convenção.
    """
    neutral_yaw: float
    neutral_pitch: float
    # Em cada extremo salvamos o delta em relação ao neutro (mais simples de
    # raciocinar). "right" = cabeça virada pra direita do usuário — valor pode
    # ser positivo OU negativo dependendo da convenção do solvePnP.
    right_yaw_delta: float   # Δyaw quando cabeça totalmente pra direita
    left_yaw_delta: float    # Δyaw quando cabeça totalmente pra esquerda
    up_pitch_delta: float    # Δpitch quando cabeça totalmente pra cima
    down_pitch_delta: float  # Δpitch quando cabeça totalmente pra baixo
    n_samples: int

    def to_dict(self) -> dict:
        return {
            "neutral_yaw":       self.neutral_yaw,
            "neutral_pitch":     self.neutral_pitch,
            "right_yaw_delta":   self.right_yaw_delta,
            "left_yaw_delta":    self.left_yaw_delta,
            "up_pitch_delta":    self.up_pitch_delta,
            "down_pitch_delta":  self.down_pitch_delta,
            "n_samples":         self.n_samples,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationProfile":
        return cls(
            neutral_yaw       =float(d["neutral_yaw"]),
            neutral_pitch     =float(d["neutral_pitch"]),
            right_yaw_delta   =float(d["right_yaw_delta"]),
            left_yaw_delta    =float(d["left_yaw_delta"]),
            up_pitch_delta    =float(d["up_pitch_delta"]),
            down_pitch_delta  =float(d["down_pitch_delta"]),
            n_samples         =int(d.get("n_samples", 0)),
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> Optional["CalibrationProfile"]:
        path = Path(path)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except Exception as e:
            print(f"[head-cal] falha ao carregar {path}: {e}", flush=True)
            return None

    # ------------------------------------------------------------------
    def normalize(self, yaw_deg: float, pitch_deg: float
                  ) -> tuple[float, float]:
        """Converte (yaw, pitch) atuais em (x, y) em [-1, 1].

        x = +1  → cabeça no extremo direito (qualquer que seja o sinal de yaw).
        x = -1  → extremo esquerdo.
        y = +1  → extremo inferior (cabeça pra baixo).
        y = -1  → extremo superior.

        Valores entre os extremos são interpolados linearmente.
        """
        dyaw   = yaw_deg   - self.neutral_yaw
        dpitch = pitch_deg - self.neutral_pitch

        # Eixo X (horizontal, via yaw)
        # Se dyaw tem o mesmo sinal de right_yaw_delta, cabeça está indo pra direita.
        if self.right_yaw_delta != 0 and _same_sign(dyaw, self.right_yaw_delta):
            denom = abs(self.right_yaw_delta) or 1e-6
            x = abs(dyaw) / denom
            x = min(1.2, x)
        elif self.left_yaw_delta != 0 and _same_sign(dyaw, self.left_yaw_delta):
            denom = abs(self.left_yaw_delta) or 1e-6
            x = -abs(dyaw) / denom
            x = max(-1.2, x)
        else:
            x = 0.0

        # Eixo Y (vertical, via pitch)
        if self.down_pitch_delta != 0 and _same_sign(dpitch, self.down_pitch_delta):
            denom = abs(self.down_pitch_delta) or 1e-6
            y = abs(dpitch) / denom
            y = min(1.2, y)
        elif self.up_pitch_delta != 0 and _same_sign(dpitch, self.up_pitch_delta):
            denom = abs(self.up_pitch_delta) or 1e-6
            y = -abs(dpitch) / denom
            y = max(-1.2, y)
        else:
            y = 0.0

        return float(x), float(y)


def _same_sign(a: float, b: float) -> bool:
    return (a >= 0 and b >= 0) or (a <= 0 and b <= 0)


# ----------------------------------------------------------------------
# Rotina de captura
# ----------------------------------------------------------------------
_STEPS = [
    ("neutral", "Olhe para FRENTE",      "Cabeça reta, relaxada. 2s."),
    ("right",   "Vire a cabeça para a DIREITA", "Até o limite CONFORTÁVEL. Segure 2s."),
    ("left",    "Vire a cabeça para a ESQUERDA","Até o limite confortável. Segure 2s."),
    ("up",      "Incline a cabeça para CIMA",   "Sem forçar o pescoço. Segure 2s."),
    ("down",    "Incline a cabeça para BAIXO",  "Segure 2s."),
]


def run_calibration(tracker: FaceTracker,
                    prep_s: float = 1.5,
                    collect_s: float = 2.0,
                    ) -> Optional[CalibrationProfile]:
    """Fluxo de 5 poses. Retorna CalibrationProfile ou None se cancelado."""
    overlay = CalibrationOverlay()
    overlay.open()
    try:
        captured: dict[str, HeadPose] = {}

        # Intro
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.5:
            k = overlay.render_message(
                "Calibração do head tracker",
                "5 passos rápidos. Siga as instruções. ESC cancela.",
            )
            if k == chr(27):
                return None

        for key, title, sub in _STEPS:
            # Preparação (tela com instrução, sem coletar)
            t0 = time.monotonic()
            while time.monotonic() - t0 < prep_s:
                k = overlay.render_message(title, sub)
                if k == chr(27):
                    return None

            # Coleta
            samples: list[HeadPose] = []
            t_start = time.monotonic()
            seen_ts = 0.0
            while (time.monotonic() - t_start) < collect_s:
                dt = time.monotonic() - t_start
                frame = tracker.last_frame()
                if frame is not None and frame.timestamp != seen_ts:
                    seen_ts = frame.timestamp
                    pose = estimate_head_pose(frame)
                    if pose is not None and pose.confidence > 0.3:
                        samples.append(pose)
                # Desenho com progresso
                prog = dt / collect_s
                _draw_progress(overlay, "CAPTURANDO: " + title.split(" para ")[-1].lower(),
                               prog, f"amostras: {len(samples)}")
                k = cv2.waitKey(16) & 0xFF
                if k == 27:
                    return None

            if len(samples) < 10:
                overlay.render_message(
                    "Amostras insuficientes",
                    f"Só {len(samples)} amostras boas para '{key}'. Tente de novo.",
                )
                time.sleep(1.5)
                return None

            # Mediana é robusta a outliers.
            yaws   = np.array([s.yaw_deg   for s in samples])
            pitchs = np.array([s.pitch_deg for s in samples])
            captured[key] = HeadPose(
                yaw_deg=float(np.median(yaws)),
                pitch_deg=float(np.median(pitchs)),
                roll_deg=0.0,
                confidence=1.0,
                tvec=np.zeros(3),
            )

        # Monta o profile.
        n = captured["neutral"]
        profile = CalibrationProfile(
            neutral_yaw      = n.yaw_deg,
            neutral_pitch    = n.pitch_deg,
            right_yaw_delta  = captured["right"].yaw_deg - n.yaw_deg,
            left_yaw_delta   = captured["left"].yaw_deg  - n.yaw_deg,
            up_pitch_delta   = captured["up"].pitch_deg  - n.pitch_deg,
            down_pitch_delta = captured["down"].pitch_deg- n.pitch_deg,
            n_samples        = 5 * 10,
        )

        # Sanity check: se algum extremo não se distanciou do neutro, a calibração falhou.
        min_range_deg = 5.0
        bads = []
        if abs(profile.right_yaw_delta) < min_range_deg: bads.append("direita")
        if abs(profile.left_yaw_delta)  < min_range_deg: bads.append("esquerda")
        if abs(profile.up_pitch_delta)  < min_range_deg: bads.append("cima")
        if abs(profile.down_pitch_delta)< min_range_deg: bads.append("baixo")
        if bads:
            overlay.render_message(
                "Range muito pequeno",
                f"As poses {', '.join(bads)} ficaram muito próximas do neutro. Refaça.",
            )
            time.sleep(2.5)
            return None

        # Confirmação
        overlay.render_message(
            "Calibração concluída",
            f"yaw: {profile.left_yaw_delta:+.0f}° ↔ {profile.right_yaw_delta:+.0f}°   "
            f"pitch: {profile.up_pitch_delta:+.0f}° ↔ {profile.down_pitch_delta:+.0f}°",
        )
        time.sleep(1.5)
        return profile
    finally:
        overlay.close()


def _draw_progress(overlay: CalibrationOverlay, text: str,
                   progress: float, sub: str = "") -> None:
    w, h = overlay.size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (15, 17, 21)
    (tw, _th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
    cv2.putText(img, text, ((w - tw) // 2, h // 2 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (230, 230, 230), 3, cv2.LINE_AA)
    bar_w = 420
    bx = (w - bar_w) // 2
    by = h // 2 + 40
    cv2.rectangle(img, (bx, by), (bx + bar_w, by + 10), (60, 70, 90), -1)
    cv2.rectangle(img, (bx, by), (bx + int(bar_w * progress), by + 10),
                  (74, 184, 90), -1)
    if sub:
        (sw, _sh), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(img, sub, ((w - sw) // 2, by + 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 160, 175), 2, cv2.LINE_AA)
    cv2.imshow(overlay.WINDOW_NAME, img)
