"""Extrai yaw/pitch/roll da cabeça (em graus) a partir de um FaceFrame.

Abordagem: `cv2.solvePnP` com 6 pontos canônicos (nariz, queixo, cantos externos
dos olhos e cantos da boca). Os mesmos pontos que o AITrack/OpenTrack usam há
anos pra head tracking.

SOLVEPNP_ITERATIVE converge bem e é estável entre frames — dá pose com ruído
muito baixo (sub-grau).
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from gaze_tracker.core.tracker import FaceFrame


# Landmarks ESTÁVEIS à deformação da boca — nariz + olhos apenas.
# Abrir/fechar a boca não move nenhum desses pontos, então o head pose fica
# isolado da expressão facial. (Os landmarks antigos incluíam queixo e cantos
# dos lábios, que se mexem quando a mandíbula cai → mira balançando ao atirar.)
HEAD_POSE_LM_STABLE = {
    "nose_tip":        1,     # ponta do nariz
    "nose_bridge_up":  6,     # entre as sobrancelhas (parte alta do dorso nasal)
    "left_eye_outer":  33,    # canto externo do olho esquerdo (da imagem)
    "left_eye_inner":  133,   # canto interno
    "right_eye_inner": 362,
    "right_eye_outer": 263,
}

# Modelo 3D canônico (mm). Valores aproximados — pequenos erros só deslocam
# a pose neutra, e a calibração de 5 poses compensa isso naturalmente.
HEAD_POSE_3D_STABLE = np.array([
    ( 0.0,    0.0,   0.0),    # nose_tip
    ( 0.0,  -42.0,  -5.0),    # nose_bridge_up (entre sobrancelhas)
    (-43.3, -33.0, -26.0),    # left_eye_outer
    (-18.0, -33.0, -22.0),    # left_eye_inner
    ( 18.0, -33.0, -22.0),    # right_eye_inner
    ( 43.3, -33.0, -26.0),    # right_eye_outer
], dtype=np.float64)


@dataclass
class HeadPose:
    yaw_deg: float       # positivo = cabeça virada pra esquerda da imagem (depende do flip)
    pitch_deg: float     # positivo = cabeça inclinada pra baixo
    roll_deg: float      # positivo = cabeça inclinando ombro direito
    confidence: float    # 0..1 — qualidade da estimativa
    tvec: np.ndarray     # translação em mm (útil pra detectar "se aproximou da câmera")


def _rotation_to_euler(R: np.ndarray) -> tuple[float, float, float]:
    """Tait-Bryan Y-X-Z (yaw, pitch, roll) em radianos."""
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


def estimate_head_pose(face: FaceFrame) -> Optional[HeadPose]:
    if face.landmarks is None or face.landmarks.shape[0] < 478:
        return None
    lm = face.landmarks[:, :2].copy()
    lm[:, 0] *= face.width
    lm[:, 1] *= face.height

    image_pts = np.array([
        lm[HEAD_POSE_LM_STABLE["nose_tip"]],
        lm[HEAD_POSE_LM_STABLE["nose_bridge_up"]],
        lm[HEAD_POSE_LM_STABLE["left_eye_outer"]],
        lm[HEAD_POSE_LM_STABLE["left_eye_inner"]],
        lm[HEAD_POSE_LM_STABLE["right_eye_inner"]],
        lm[HEAD_POSE_LM_STABLE["right_eye_outer"]],
    ], dtype=np.float64)

    focal = float(face.width)
    cam_mat = np.array([
        [focal, 0, face.width / 2.0],
        [0, focal, face.height / 2.0],
        [0, 0, 1],
    ], dtype=np.float64)
    dist = np.zeros((4, 1))

    ok, rvec, tvec = cv2.solvePnP(
        HEAD_POSE_3D_STABLE, image_pts, cam_mat, dist,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return None

    R, _ = cv2.Rodrigues(rvec)
    yaw, pitch, roll = _rotation_to_euler(R)

    # Reprojection error dá confiança. Projetamos os pontos 3D com a pose e
    # medimos distância em pixels até os 2D originais.
    projected, _ = cv2.projectPoints(HEAD_POSE_3D_STABLE, rvec, tvec, cam_mat, dist)
    err_px = float(np.mean(np.linalg.norm(projected.reshape(-1, 2) - image_pts, axis=1)))
    # Threshold generoso; a maioria cai <5 px. 15 px = já está precário.
    conf = float(max(0.0, 1.0 - err_px / 15.0))

    return HeadPose(
        yaw_deg=float(np.degrees(yaw)),
        pitch_deg=float(np.degrees(pitch)),
        roll_deg=float(np.degrees(roll)),
        confidence=conf,
        tvec=tvec.reshape(-1),
    )
