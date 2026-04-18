"""Modo ação — rotação da cabeça controla câmera (via engine), boca aberta atira.

Voz: 'modo acao' liga, 'desativar modo acao' desliga.

Arquitetura engine-first:
  - HeadTracker roda local (MediaPipe + webcam).
  - Loop de 30Hz lê `direction` normalizada e envia `camera_set {x,y}` pra
    resource FiveM. O TICK DO CLIENT.LUA aplica rotação a 60Hz, suavemente.
  - MouthDetector dispara callback → POST `shoot {hold: true/false}` pra
    resource, que mantém RMB+LMB pressionados pelo tempo que a boca ficar aberta.
  - Aim assist é ligado/desligado no resource: `aim_assist_on / aim_assist_off`.

Vantagens vs. abordagem anterior (pynput):
  - Câmera nativa = mais estável, sem depender do Windows entregar mouse pro jogo.
  - Aim assist só é viável com acesso a entidades in-game (ped hostil, bone da cabeça).
  - Se o resource não estiver rodando, o brain loga e não explode.
"""

import threading
import time
from typing import Optional


class ActionMode:
    def __init__(
        self,
        camera_index: int = 0,
        dead_zone: float = 0.10,
        tick_hz: int = 30,
        bridge=None,
        on_status: Optional[callable] = None,
    ) -> None:
        """
        camera_index — índice da webcam.
        dead_zone    — fração [0..1] do range calibrado sem movimento (anti-jitter).
        tick_hz      — frequência com que atualiza a câmera no resource.
        bridge       — FiveMBridge (obrigatório pra rotação de câmera).
        """
        self.camera_index = camera_index
        self.dead_zone = dead_zone
        self.tick_hz = tick_hz
        self._on_status = on_status or (lambda s: None)
        self._bridge = bridge
        self._cam_stream = None  # CameraStream (lazy)

        self._tracker = None
        self._active = False
        self._mouth_firing = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def set_bridge(self, bridge) -> None:
        self._bridge = bridge

    def is_active(self) -> bool:
        return self._active

    def has_neutral(self) -> bool:
        ht = self._ensure_tracker()
        return ht.has_profile()

    def _ensure_tracker(self):
        if self._tracker is None:
            try:
                from head_tracker import HeadTracker
            except ImportError as e:
                raise RuntimeError(
                    "head_tracker não importável. Instale deps: "
                    "pip install -r head_tracker/requirements.txt"
                ) from e
            self._tracker = HeadTracker(camera_index=self.camera_index)
        return self._tracker

    def _ensure_cam_stream(self):
        if self._cam_stream is None and self._bridge is not None:
            from bridge.fivem import CameraStream
            self._cam_stream = CameraStream(self._bridge)
        return self._cam_stream

    # ------------------------------------------------------------------
    def recalibrate(self) -> bool:
        ht = self._ensure_tracker()
        self._on_status("calibrating")
        ok = ht.run_calibration()
        self._on_status("calibrated" if ok else "calibration_failed")
        return ok

    # ------------------------------------------------------------------
    def activate(self) -> bool:
        if self._bridge is None:
            print("[action] sem bridge FiveM — modo ação requer resource carregada", flush=True)
            self._on_status("no_bridge")
            return False
        with self._lock:
            if self._active:
                return True
            ht = self._ensure_tracker()

            if not ht.has_profile():
                self._on_status("needs_calibration")
                ok = ht.run_calibration()
                if not ok:
                    return False

            ht.start()
            ht.set_mouth_callback(self._on_mouth)

            # Avisa resource pra ligar aim assist
            self._bridge.send_async("aim_assist_on")

            self._stop.clear()
            self._thread = threading.Thread(target=self._camera_loop, daemon=True)
            self._thread.start()
            self._active = True
        self._on_status("activated")
        return True

    def deactivate(self) -> None:
        with self._lock:
            if not self._active:
                return
            self._stop.set()
            self._active = False

            # Solta mouth firing no resource
            if self._mouth_firing and self._bridge is not None:
                self._bridge.send_async("shoot", hold=False)
                self._mouth_firing = False

            # Zera câmera + desliga aim assist
            if self._bridge is not None:
                self._bridge.send_async("camera_stop")
                self._bridge.send_async("aim_assist_off")

            if self._tracker is not None:
                self._tracker.set_mouth_callback(lambda o: None)
                self._tracker.stop()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._on_status("deactivated")

    # ------------------------------------------------------------------
    def _on_mouth(self, is_open: bool) -> None:
        if not self._active or self._bridge is None:
            return
        if is_open and not self._mouth_firing:
            self._bridge.send_async("shoot", hold=True)
            self._mouth_firing = True
            self._on_status("firing_on")
        elif not is_open and self._mouth_firing:
            self._bridge.send_async("shoot", hold=False)
            self._mouth_firing = False
            self._on_status("firing_off")

    # ------------------------------------------------------------------
    def _camera_loop(self) -> None:
        """Lê a direção da cabeça e streama pro resource FiveM."""
        assert self._tracker is not None
        ht = self._tracker
        stream = self._ensure_cam_stream()
        if stream is None:
            return

        period = 1.0 / max(1, self.tick_hz)
        next_tick = time.monotonic() + period

        while not self._stop.is_set():
            d = ht.get_direction()
            if d is not None and d.confidence > 0.3:
                x = self._apply_dead_zone(d.x)
                y = self._apply_dead_zone(d.y)
                stream.set(x, y)
            else:
                stream.set(0.0, 0.0)

            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            next_tick += period
            if next_tick < time.monotonic():
                next_tick = time.monotonic() + period

        # Ao sair, força câmera parada.
        stream.stop()

    def _apply_dead_zone(self, n: float) -> float:
        if abs(n) <= self.dead_zone:
            return 0.0
        sign = 1.0 if n > 0 else -1.0
        mag = (abs(n) - self.dead_zone) / max(1e-6, 1.0 - self.dead_zone)
        mag = min(1.0, mag)
        return sign * mag
