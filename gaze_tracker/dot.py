"""Validação visual da calibração — mostra um ponto vermelho sempre no topo
seguindo seu olhar em tempo real.

Rodar:
    python -m gaze_tracker.dot
    python -m gaze_tracker.dot 1      # câmera no índice 1

Atalhos na janela preta pequena (foco nela):
    ESC — sai
    R   — recalibra (fullscreen 9 pontos)
    Q   — recalibração rápida (5 pontos)

O ponto vermelho fica "sempre no topo" em cima de qualquer app.
Pra validar: olhe pro canto superior esquerdo → o ponto vai pra perto de (0,0).
Canto inferior direito → vai pra perto da resolução.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from gaze_tracker import GazeTracker


DOT_SIZE = 30  # px — tamanho da janela do ponto


def main() -> None:
    cam_idx = int(os.environ.get("GAZE_CAM_INDEX",
                                 sys.argv[1] if len(sys.argv) > 1 else "0"))
    print(f"[dot] webcam índice {cam_idx}")

    gt = GazeTracker(camera_index=cam_idx)
    gt.start()

    # Se nunca calibrou, calibra agora (bloqueia até terminar)
    if not gt.is_calibrated():
        print("[dot] sem calibração — rodando calibração completa primeiro.")
        ok = gt.run_calibration(quick=False)
        if not ok:
            print("[dot] calibração cancelada, saindo.")
            gt.stop()
            return

    # ---------------------- janela do ponto (topmost) ----------------------
    dot = tk.Tk()
    dot.title("gaze")
    dot.overrideredirect(True)             # sem moldura
    dot.attributes("-topmost", True)       # sempre acima de tudo
    # Fundo preto que vira transparente (Windows-only, mas o pacote é Windows-first)
    try:
        dot.attributes("-transparentcolor", "black")
    except Exception:
        pass
    dot.configure(bg="black")
    dot.geometry(f"{DOT_SIZE}x{DOT_SIZE}+100+100")

    canvas = tk.Canvas(dot, width=DOT_SIZE, height=DOT_SIZE, bg="black",
                       highlightthickness=0)
    canvas.pack()
    canvas.create_oval(3, 3, DOT_SIZE - 3, DOT_SIZE - 3,
                       fill="#ff3030", outline="#ffffff", width=2)

    # ---------------------- janelinha de controle --------------------------
    ctrl = tk.Toplevel(dot)
    ctrl.title("gaze — controles")
    ctrl.attributes("-topmost", True)
    ctrl.geometry("340x120+20+20")
    ctrl.configure(bg="#181b22")
    lbl = tk.Label(ctrl, text="Foque ESTA janela para usar atalhos.\n"
                              "R = calibração completa (9 pts)\n"
                              "Q = calibração rápida (5 pts)\n"
                              "ESC = sair",
                   bg="#181b22", fg="#e7eaf1", justify="left", anchor="w",
                   padx=12, pady=10)
    lbl.pack(fill="both", expand=True)

    # ---------------------- eventos ----------------------------------------
    def on_key(event):
        k = event.keysym.lower()
        if k == "escape":
            shutdown()
        elif k == "r":
            threading.Thread(
                target=lambda: gt.run_calibration(quick=False), daemon=True
            ).start()
        elif k == "q":
            threading.Thread(
                target=lambda: gt.run_calibration(quick=True), daemon=True
            ).start()

    def shutdown():
        try: gt.stop()
        except Exception: pass
        try: dot.destroy()
        except Exception: pass

    ctrl.bind("<Key>", on_key)
    ctrl.protocol("WM_DELETE_WINDOW", shutdown)
    dot.protocol("WM_DELETE_WINDOW", shutdown)

    # ---------------------- loop de update ---------------------------------
    def update():
        g = gt.get_gaze()
        if g is not None:
            x = int(g.x - DOT_SIZE // 2)
            y = int(g.y - DOT_SIZE // 2)
            dot.geometry(f"{DOT_SIZE}x{DOT_SIZE}+{x}+{y}")
        dot.after(30, update)

    update()
    ctrl.focus_force()
    dot.mainloop()


if __name__ == "__main__":
    main()
