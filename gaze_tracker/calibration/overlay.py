"""Overlay fullscreen com cv2 pra mostrar pontos de calibração.

Usa cv2.namedWindow + WINDOW_FULLSCREEN. Renderiza a cada frame.
Thread principal pode bloquear enquanto a calibração roda — o FaceTracker continua
capturando em thread daemon em paralelo.
"""

import time
from typing import Optional

import cv2
import numpy as np


def _screen_size() -> tuple[int, int]:
    """Tenta descobrir tamanho do monitor primário.

    No Windows, usa GetSystemMetrics. Fallback: 1920x1080.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return int(w), int(h)
    except Exception:
        pass
    return 1920, 1080


def grid_points(w: int, h: int, n: int = 9, margin_ratio: float = 0.12
                ) -> list[tuple[int, int]]:
    """Retorna lista de pontos de calibração em coordenadas de pixel."""
    mx = int(w * margin_ratio)
    my = int(h * margin_ratio)
    xs = [mx, w // 2, w - mx]
    ys = [my, h // 2, h - my]
    pts_9 = [(x, y) for y in ys for x in xs]
    if n >= 9:
        return pts_9
    if n == 5:
        # centro + 4 cantos
        return [pts_9[0], pts_9[2], pts_9[4], pts_9[6], pts_9[8]]
    # mínimo: canto + centro + canto
    return [pts_9[0], pts_9[4], pts_9[8]]


class CalibrationOverlay:
    WINDOW_NAME = "gaze_tracker_calibration"

    def __init__(self) -> None:
        self._w, self._h = _screen_size()
        self._active = False

    @property
    def size(self) -> tuple[int, int]:
        return self._w, self._h

    def open(self) -> None:
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        # Tenta manter janela no topo (nem toda build do OpenCV tem essa flag).
        topmost_flag = getattr(cv2, "WND_PROP_TOPMOST", None)
        if topmost_flag is not None:
            try: cv2.setWindowProperty(self.WINDOW_NAME, topmost_flag, 1)
            except Exception: pass
        self._active = True

    def close(self) -> None:
        if self._active:
            cv2.destroyWindow(self.WINDOW_NAME)
            self._active = False

    def render_point(self, x: int, y: int, radius_px: int = 24,
                     hint: str = "", progress: float = 0.0) -> Optional[str]:
        """Desenha o ponto-alvo. Retorna tecla pressionada (ou None)."""
        img = np.zeros((self._h, self._w, 3), dtype=np.uint8)
        img[:] = (15, 17, 21)  # mesmo fundo escuro da UI web

        # Pulso do ponto (anima pra chamar atenção)
        t = time.monotonic()
        pulse = 1.0 + 0.25 * np.sin(t * 6.0)
        r = max(4, int(radius_px * pulse))
        cv2.circle(img, (x, y), r + 10, (47, 111, 224), 2)
        cv2.circle(img, (x, y), r, (79, 140, 255), -1)
        # Miolo
        cv2.circle(img, (x, y), max(2, r // 4), (255, 255, 255), -1)

        # Barra de progresso abaixo do ponto
        if 0.0 < progress <= 1.0:
            bar_w, bar_h = 180, 6
            bx = x - bar_w // 2
            by = y + r + 22
            cv2.rectangle(img, (bx, by), (bx + bar_w, by + bar_h), (60, 70, 90), -1)
            cv2.rectangle(img, (bx, by), (bx + int(bar_w * progress), by + bar_h),
                          (74, 184, 90), -1)

        # Dica central
        if hint:
            (tw, th), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.putText(img, hint,
                        ((self._w - tw) // 2, self._h - 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2,
                        cv2.LINE_AA)

        cv2.imshow(self.WINDOW_NAME, img)
        key = cv2.waitKey(16) & 0xFF
        return chr(key) if key != 255 else None

    def render_message(self, text: str, sub: str = "") -> Optional[str]:
        img = np.zeros((self._h, self._w, 3), dtype=np.uint8)
        img[:] = (15, 17, 21)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
        cv2.putText(img, text,
                    ((self._w - tw) // 2, self._h // 2 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (230, 230, 230), 3, cv2.LINE_AA)
        if sub:
            (sw, _sh), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.putText(img, sub,
                        ((self._w - sw) // 2, self._h // 2 + 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 160, 175), 2, cv2.LINE_AA)
        cv2.imshow(self.WINDOW_NAME, img)
        key = cv2.waitKey(16) & 0xFF
        return chr(key) if key != 255 else None
