"""Converte landmarks do Face Mesh em features de olhar.

Features finais (shape (4,)):
  iris_x, iris_y          — offset da íris dentro do bounding box dos dois olhos,
                             em [-1,1] x [-1,1] (média dos dois olhos).
  yaw, pitch              — ângulos da cabeça em radianos, via solvePnP.

A regressão depois mapeia (iris_x, iris_y, yaw, pitch) → (screen_x, screen_y).
Head pose entra como feature: movimento de cabeça vira entrada do modelo em vez de ruído.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from gaze_tracker.core.tracker import (
    FaceFrame,
    HEAD_POSE_3D,
    HEAD_POSE_LM,
    LEFT_EYE_INNER,
    LEFT_EYE_OUTER,
    LEFT_IRIS_CENTER,
    RIGHT_EYE_INNER,
    RIGHT_EYE_OUTER,
    RIGHT_IRIS_CENTER,
)


@dataclass
class GazeFeatures:
    iris_x: float       # [-1, 1] horizontal (negativo = olhando p/ esquerda da tela)
    iris_y: float       # [-1, 1] vertical   (negativo = olhando p/ cima)
    yaw: float          # rad, positivo = cabeça virada pra direita do observador
    pitch: float        # rad, positivo = cabeça inclinada pra baixo
    roll: float         # rad, positivo = cabeça inclinando p/ ombro direito
    confidence: float   # 0..1 — qualidade do sinal (olhos abertos, face detectada)

    def as_array(self) -> np.ndarray:
        return np.array([self.iris_x, self.iris_y, self.yaw, self.pitch],
                        dtype=np.float64)


def _iris_offset_one_eye(lm_xy: np.ndarray,
                         iris_idx: int, outer_idx: int, inner_idx: int,
                         ) -> tuple[float, float]:
    """Offset da íris dentro do segmento horizontal do olho, em [-1, 1].

    X: -1 no canto externo, +1 no canto interno (pro olho direito; pro olho
    esquerdo invertemos no caller). Convertido pra sinal "da tela" pelo caller.
    Y: -1 acima do centro, +1 abaixo.
    """
    iris = lm_xy[iris_idx]
    o, i = lm_xy[outer_idx], lm_xy[inner_idx]
    # Eixo X = direção do olho (outer -> inner). Projeta iris nesse eixo.
    axis_x = i - o
    eye_len = np.linalg.norm(axis_x) + 1e-9
    ux = axis_x / eye_len
    # offset projetado; t=0 no outer, t=1 no inner.
    t = float(np.dot(iris - o, ux) / eye_len)
    # normaliza pra [-1..+1] com centro em 0.5
    nx = (t - 0.5) * 2.0

    # Y: usa altura do olho aproximada (distância do iris à linha outer-inner).
    # Como não temos top/bottom landmarks aqui, aproximamos pela distância
    # perpendicular dividida por eye_len*0.4 (proporção olho altura/largura).
    perp = iris - o - ux * (t * eye_len)
    # sinal vertical: Y cresce pra baixo no image frame.
    ny = float(perp[1] / (eye_len * 0.4 + 1e-9))
    ny = float(np.clip(ny, -1.5, 1.5))
    nx = float(np.clip(nx, -1.5, 1.5))
    return nx, ny


def _iris_features(lm_xy: np.ndarray) -> tuple[float, float]:
    # Olho direito do sujeito (esquerdo na imagem por causa do flip do tracker)
    # outer = 33, inner = 133, iris = 468 (em MediaPipe 'LEFT_' refere-se ao lado
    # esquerdo do modelo; com flip horizontal, já invertemos).
    rx, ry = _iris_offset_one_eye(lm_xy, LEFT_IRIS_CENTER, LEFT_EYE_OUTER, LEFT_EYE_INNER)
    lx, ly = _iris_offset_one_eye(lm_xy, RIGHT_IRIS_CENTER, RIGHT_EYE_OUTER, RIGHT_EYE_INNER)
    # Para o olho "esquerdo do modelo" (LEFT_*), o outer->inner aponta pra
    # direita do rosto; pro outro, aponta pra esquerda. Invertendo um deles
    # pra ficarem coerentes: positivo = íris deslocada pra direita da tela.
    # (LEFT_EYE vai de 33=outer (direita da tela) até 133=inner (centro) —
    #  positivo na convenção já representa "íris mais perto do centro".)
    # Simplificação: se o usuário olha pra esquerda, ambas as íris vão pra
    # esquerda; tiramos a média após alinhar sinais.
    rx_aligned = -rx   # inverter o olho "esquerdo do modelo" pra "olhando pra esquerda = negativo"
    ix = (rx_aligned + lx) * 0.5
    iy = (ry + ly) * 0.5
    return float(ix), float(iy)


def _head_pose(lm_xy_px: np.ndarray, w: int, h: int
               ) -> tuple[float, float, float]:
    """Yaw, pitch, roll em radianos via solvePnP."""
    image_pts = np.array([
        lm_xy_px[HEAD_POSE_LM["nose_tip"]],
        lm_xy_px[HEAD_POSE_LM["chin"]],
        lm_xy_px[HEAD_POSE_LM["left_eye"]],
        lm_xy_px[HEAD_POSE_LM["right_eye"]],
        lm_xy_px[HEAD_POSE_LM["left_mouth"]],
        lm_xy_px[HEAD_POSE_LM["right_mouth"]],
    ], dtype=np.float64)

    focal = float(w)  # aproximação sem calibração de câmera
    cam_mat = np.array([
        [focal, 0, w / 2.0],
        [0, focal, h / 2.0],
        [0, 0, 1],
    ], dtype=np.float64)
    dist = np.zeros((4, 1))

    ok, rvec, _ = cv2.solvePnP(
        HEAD_POSE_3D, image_pts, cam_mat, dist,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return 0.0, 0.0, 0.0

    R, _ = cv2.Rodrigues(rvec)
    # Extrai yaw/pitch/roll (convenção Y-X-Z) a partir da rotação.
    # sy = sqrt(R[0,0]^2 + R[1,0]^2)
    sy = float(np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2))
    singular = sy < 1e-6
    if not singular:
        pitch = float(np.arctan2(R[2, 1], R[2, 2]))
        yaw   = float(np.arctan2(-R[2, 0], sy))
        roll  = float(np.arctan2(R[1, 0], R[0, 0]))
    else:
        pitch = float(np.arctan2(-R[1, 2], R[1, 1]))
        yaw   = float(np.arctan2(-R[2, 0], sy))
        roll  = 0.0
    return yaw, pitch, roll


def compute_features(face: FaceFrame) -> Optional[GazeFeatures]:
    if face.landmarks is None or face.landmarks.shape[0] < 478:
        return None
    lm_norm = face.landmarks[:, :2]
    lm_px = lm_norm.copy()
    lm_px[:, 0] *= face.width
    lm_px[:, 1] *= face.height

    ix, iy = _iris_features(lm_norm)
    yaw, pitch, roll = _head_pose(lm_px, face.width, face.height)

    # Confiança heurística: 1.0 se head pose razoável e íris dentro do range.
    conf = 1.0
    if abs(yaw) > np.radians(35) or abs(pitch) > np.radians(30):
        conf *= 0.5  # cabeça muito virada → precisão cai
    if abs(ix) > 1.2 or abs(iy) > 1.2:
        conf *= 0.5
    return GazeFeatures(
        iris_x=ix, iris_y=iy, yaw=yaw, pitch=pitch, roll=roll, confidence=conf,
    )
