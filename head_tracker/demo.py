"""Demo standalone do head_tracker.

    python -m head_tracker.demo         # câmera índice 0
    python -m head_tracker.demo 1       # índice 1

Mostra:
  - Preview da webcam.
  - Cruz vermelha representando yaw/pitch (relativos à pose neutra).
  - Barras de referência em ±25° pra você ver o range.
  - Estado da boca (ABERTA / fechada).
  - Atalhos: N = recaptura pose neutra | ESC = sai.
"""

import os
import sys
import time

import cv2

from head_tracker import HeadTracker


def draw_hud(img, direction, mouth_open: bool, fps: float):
    h, w = img.shape[:2]
    panel_w = 190
    panel = img[:, w - panel_w:]
    panel[:] = (20, 22, 28)

    def put(txt, y, color=(220, 220, 220), size=0.45, thick=1):
        cv2.putText(img, txt, (w - panel_w + 10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, size, color, thick, cv2.LINE_AA)

    put("HEAD TRACKER", 22, (180, 200, 255), 0.5, 1)
    put(f"fps: {fps:.0f}", 46)
    if direction is None:
        put("sem calibração.", 74, (240, 180, 80))
        put("pressione C", 92, (240, 180, 80))
        return

    put(f"x:     {direction.x:+.2f}", 78)
    put(f"y:     {direction.y:+.2f}", 96)
    put(f"Δyaw:  {direction.dyaw_deg:+6.1f}°", 120)
    put(f"Δpitch:{direction.dpitch_deg:+6.1f}°", 138)
    put(f"conf:  {direction.confidence:.2f}", 156)

    tag = "BOCA ABERTA" if mouth_open else "boca fechada"
    color = (60, 220, 60) if mouth_open else (150, 150, 150)
    put(tag, 190, color, 0.55, 2)


def draw_crosshair(img, direction):
    """Desenha alvo circular com a cruz em (x, y) normalizado.

    x=+1 → crosshair encostado na direita do alvo.
    y=+1 → crosshair encostado embaixo.
    Se a calibração estiver correta, virar a cabeça pra direita move a cruz pra
    direita — e só.
    """
    h, w = img.shape[:2]
    cx, cy = w // 2 - 100, h // 2
    radius = min(w, h) // 3

    # Fundo do alvo
    cv2.circle(img, (cx, cy), radius, (40, 48, 60), 1)
    cv2.circle(img, (cx, cy), int(radius * 0.66), (40, 48, 60), 1)
    cv2.circle(img, (cx, cy), int(radius * 0.33), (40, 48, 60), 1)
    cv2.line(img, (cx - radius, cy), (cx + radius, cy), (40, 48, 60), 1)
    cv2.line(img, (cx, cy - radius), (cx, cy + radius), (40, 48, 60), 1)

    if direction is None:
        return

    fx = max(-1.2, min(1.2, direction.x))
    fy = max(-1.2, min(1.2, direction.y))
    px = int(cx + fx * radius)
    py = int(cy + fy * radius)

    color = (60, 80, 255)
    cv2.circle(img, (px, py), 10, color, 2)
    cv2.line(img, (px - 14, py), (px + 14, py), color, 2)
    cv2.line(img, (px, py - 14), (px, py + 14), color, 2)


def main() -> None:
    cam_idx = int(os.environ.get("GAZE_CAM_INDEX",
                                 sys.argv[1] if len(sys.argv) > 1 else "0"))
    print(f"[demo] webcam índice {cam_idx}")
    ht = HeadTracker(camera_index=cam_idx)
    ht.start()
    print("[demo] aguardando webcam...")
    time.sleep(1.0)

    if not ht.has_profile():
        print("[demo] sem calibração — rodando agora (5 poses).")
        ok = ht.run_calibration()
        if not ok:
            print("[demo] calibração cancelada, saindo.")
            ht.stop()
            return

    ht.set_mouth_callback(lambda o: print(f"[demo] mouth -> {'OPEN' if o else 'close'}"))

    print("[demo] rodando.  C=recalibrar (5 poses)  ESC=sair")
    try:
        while True:
            frame = ht._tracker.last_frame()
            if frame is None or frame.image is None:
                time.sleep(0.02)
                continue
            img = frame.image.copy()
            direction = ht.get_direction()
            draw_crosshair(img, direction)
            draw_hud(img, direction, ht.get_mouth_is_open(), ht.get_fps())

            cv2.imshow("head_tracker demo", img)
            key = cv2.waitKey(16) & 0xFF
            if key == 27:
                break
            if key in (ord("c"), ord("C")):
                print("[demo] recalibrando...")
                ht.run_calibration()
    finally:
        ht.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
