"""Demo standalone do gaze_tracker.

Roda: python -m gaze_tracker.demo

- Pede calibração se ainda não calibrou.
- Abre uma janela com o preview da webcam e desenha landmarks de íris + boca.
- Mostra coordenadas do gaze atual e estado da boca.
- C: recalibra (5 pontos). R: recalibra completo. ESC: sai.
"""

import time

import cv2

from gaze_tracker import GazeTracker
from gaze_tracker.core.tracker import (
    LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER,
    UPPER_LIP_INNER, LOWER_LIP_INNER, LIP_CORNER_L, LIP_CORNER_R,
)


def draw_overlay(frame, landmarks, mouth_open: bool):
    h, w = frame.shape[:2]
    pts = {
        "iris_L": landmarks[LEFT_IRIS_CENTER, :2],
        "iris_R": landmarks[RIGHT_IRIS_CENTER, :2],
        "lip_up": landmarks[UPPER_LIP_INNER, :2],
        "lip_lo": landmarks[LOWER_LIP_INNER, :2],
        "lip_cl": landmarks[LIP_CORNER_L, :2],
        "lip_cr": landmarks[LIP_CORNER_R, :2],
    }
    for name, p in pts.items():
        x, y = int(p[0] * w), int(p[1] * h)
        color = (0, 180, 255) if name.startswith("iris") else (120, 255, 120)
        cv2.circle(frame, (x, y), 3, color, -1)
    tag = "BOCA ABERTA" if mouth_open else "boca fechada"
    cv2.putText(frame, tag, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (60, 210, 60) if mouth_open else (160, 160, 160), 2, cv2.LINE_AA)


def main() -> None:
    import os, sys
    cam_idx = int(os.environ.get("GAZE_CAM_INDEX", sys.argv[1] if len(sys.argv) > 1 else "0"))
    print(f"[demo] usando webcam índice {cam_idx} "
          f"(mude com: python -m gaze_tracker.demo <idx> ou GAZE_CAM_INDEX=<idx>)")
    gt = GazeTracker(camera_index=cam_idx)
    gt.start()
    print("[demo] aguardando webcam inicializar...")
    time.sleep(1.0)

    if not gt.is_calibrated():
        print("[demo] sem calibração salva — rodando calibração completa agora.")
        ok = gt.run_calibration(quick=False)
        if not ok:
            print("[demo] calibração cancelada. Saindo.")
            gt.stop()
            return

    gt.set_mouth_callback(lambda o: print(f"[demo] mouth -> {'OPEN' if o else 'close'}"))

    print("[demo] rodando. C=rec rápida  R=rec completa  ESC=sair")
    try:
        while True:
            frame = gt._tracker.last_frame()
            if frame is None or frame.image is None:
                time.sleep(0.02)
                continue
            img = frame.image.copy()
            draw_overlay(img, frame.landmarks, gt.get_mouth_is_open())

            g = gt.get_gaze()
            if g:
                label = f"gaze=({g.x:.0f}, {g.y:.0f})  conf={g.confidence:.2f}  fps={gt.get_fps():.0f}"
                cv2.putText(img, label, (12, img.shape[0] - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 220, 255), 1,
                            cv2.LINE_AA)

            cv2.imshow("gaze_tracker demo", img)
            key = cv2.waitKey(16) & 0xFF
            if key == 27:
                break
            if key in (ord("c"), ord("C")):
                print("[demo] recalibração rápida")
                gt.run_calibration(quick=True)
            if key in (ord("r"), ord("R")):
                print("[demo] recalibração completa")
                gt.run_calibration(quick=False)
    finally:
        gt.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
