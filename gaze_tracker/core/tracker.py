"""Webcam + MediaPipe Face Mesh (com refinamento de íris).

Produz, por frame capturado:
  - 478 landmarks normalizados em [0,1] (x, y, z)
  - bitmap do frame pra debug/overlay
  - timestamp monotônico
O resto do pacote consome esses landmarks.
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

try:
    import mediapipe as mp
    # Algumas versões / distros do mediapipe não expõem `solutions` no top-level.
    # Tentamos importar via caminhos alternativos e colamos de volta no `mp`.
    if not hasattr(mp, "solutions"):
        try:
            from mediapipe.python import solutions as _mp_solutions
        except ImportError:
            from mediapipe import solutions as _mp_solutions  # type: ignore
        mp.solutions = _mp_solutions  # type: ignore[attr-defined]
except ImportError as e:
    raise ImportError(
        "mediapipe não instalado. Rode: pip install -r gaze_tracker/requirements.txt"
    ) from e
except Exception as e:
    raise ImportError(
        f"mediapipe encontrado mas sem `solutions` — versão instalada incompatível. "
        f"Tente: pip install 'mediapipe>=0.10.9,<0.11'. Erro original: {e}"
    ) from e


@dataclass
class FaceFrame:
    # Landmarks como array Nx3 em coordenadas normalizadas [0,1] de imagem.
    landmarks: np.ndarray
    # Frame BGR (pode ser None se não foi capturado com render=True).
    image: Optional[np.ndarray]
    width: int
    height: int
    timestamp: float


# Índices relevantes no MediaPipe Face Mesh (com refine_landmarks=True)
# Íris — refinada dá landmarks 468-477 (5 por olho).
# https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png
LEFT_IRIS_CENTER  = 468   # centro da íris esquerda (referencial do espelho → seu olho direito)
RIGHT_IRIS_CENTER = 473   # centro da íris direita

# Cantos do olho (pra bounding box por olho)
LEFT_EYE_OUTER  = 33
LEFT_EYE_INNER  = 133
RIGHT_EYE_OUTER = 263
RIGHT_EYE_INNER = 362

# Lábios (pra MAR)
UPPER_LIP_INNER = 13
LOWER_LIP_INNER = 14
LIP_CORNER_L    = 78
LIP_CORNER_R    = 308

# Pontos pra solvePnP (head pose). Usamos os canônicos documentados.
HEAD_POSE_LM = {
    "nose_tip":    1,
    "chin":        152,
    "left_eye":    33,
    "right_eye":   263,
    "left_mouth":  61,
    "right_mouth": 291,
}

# Modelo 3D canônico em mm, origem no nariz, X direita, Y baixo, Z atrás.
# Valores padrão MediaPipe-compatíveis (ordem alinhada com HEAD_POSE_LM).
HEAD_POSE_3D = np.array([
    ( 0.0,    0.0,    0.0),    # nose_tip
    ( 0.0,   63.6,  -12.5),    # chin
    (-43.3,  -32.7, -26.0),    # left_eye
    ( 43.3,  -32.7, -26.0),    # right_eye
    (-28.9,  28.9,  -24.1),    # left_mouth
    ( 28.9,  28.9,  -24.1),    # right_mouth
], dtype=np.float64)


class FaceTracker:
    def __init__(
        self,
        camera_index: int = 0,
        frame_width: int = 640,
        frame_height: int = 480,
        flip_horizontal: bool = True,
    ) -> None:
        self._cam_idx = camera_index
        self._w = frame_width
        self._h = frame_height
        self._flip = flip_horizontal

        self._mp = mp.solutions.face_mesh
        self._face = self._mp.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,   # ATIVA landmarks de íris 468-477
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last: Optional[FaceFrame] = None
        self._listener: Optional[Callable[[FaceFrame], None]] = None
        self._fps_samples: list[float] = []

    # ------------------------------------------------------------------
    def set_listener(self, fn: Callable[[FaceFrame], None]) -> None:
        self._listener = fn

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def last_frame(self) -> Optional[FaceFrame]:
        with self._lock:
            return self._last

    def fps(self) -> float:
        if not self._fps_samples:
            return 0.0
        return len(self._fps_samples) / max(1e-6, sum(self._fps_samples))

    # ------------------------------------------------------------------
    def _open_cam(self) -> cv2.VideoCapture:
        """Tenta múltiplos backends. No Windows 11 o CAP_DSHOW às vezes falha;
        CAP_MSMF (Media Foundation) tende a funcionar melhor em câmeras modernas."""
        backends = [
            ("CAP_MSMF", cv2.CAP_MSMF),
            ("CAP_DSHOW", cv2.CAP_DSHOW),
            ("CAP_ANY", cv2.CAP_ANY),
        ]
        last_err = None
        for name, backend in backends:
            try:
                cap = cv2.VideoCapture(self._cam_idx, backend)
                if not cap.isOpened():
                    cap.release()
                    last_err = f"{name}: isOpened=False"
                    continue
                # Precisa ler 1 frame pra ter certeza que funciona — algumas
                # câmeras dão isOpened=True mas retornam frames vazios.
                ok, frame = cap.read()
                if not ok or frame is None:
                    cap.release()
                    last_err = f"{name}: 1º read falhou"
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._h)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print(f"[face-tracker] webcam {self._cam_idx} aberta via {name}", flush=True)
                return cap
            except Exception as e:
                last_err = f"{name}: {e}"
                continue
        raise RuntimeError(
            f"webcam {self._cam_idx} não abriu em nenhum backend. Último erro: {last_err}. "
            f"Verifique: (1) câmera conectada; (2) nenhum outro app usando; "
            f"(3) Configurações → Privacidade → Câmera → permitir apps desktop."
        )

    def _loop(self) -> None:
        try:
            self._cap = self._open_cam()
        except Exception as e:
            print(f"[face-tracker] falha abrindo webcam: {e}", flush=True)
            return

        last_t = time.monotonic()
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            if self._flip:
                frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            result = self._face.process(rgb)

            h, w = frame.shape[:2]
            if result.multi_face_landmarks:
                lm = result.multi_face_landmarks[0].landmark
                arr = np.array([(p.x, p.y, p.z) for p in lm], dtype=np.float32)
                face_frame = FaceFrame(
                    landmarks=arr, image=frame, width=w, height=h,
                    timestamp=time.monotonic(),
                )
                with self._lock:
                    self._last = face_frame
                if self._listener:
                    try: self._listener(face_frame)
                    except Exception as e:
                        print(f"[face-tracker] listener err: {e}", flush=True)

            now = time.monotonic()
            self._fps_samples.append(now - last_t)
            if len(self._fps_samples) > 60:
                self._fps_samples.pop(0)
            last_t = now
