"""Bridge HTTP: Python → resource FiveM acessibilidade_gta.

Endpoint único: POST {base_url}/acessibilidade_gta/command
Body: {"action": "<nome>", ...params}

O resource trata dispatch pro client.lua. Timeouts curtos porque é localhost
e não bloqueamos nada se o servidor FiveM estiver offline.
"""

import threading
import time
from typing import Any, Optional

try:
    import urllib.request
    import urllib.error
    import json
except ImportError as e:  # pragma: no cover
    raise


class FiveMBridge:
    """Cliente HTTP enxuto. Usa urllib pra não adicionar dependência (requests).
    Stateful: lembra se a última chamada falhou pra não spam-logar.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:30120",
                 timeout_s: float = 1.5) -> None:
        self._url = f"{base_url.rstrip('/')}/acessibilidade_gta/command"
        self._timeout = timeout_s
        self._last_ok = True
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return self._url

    def send(self, action: str, **params: Any) -> bool:
        """Envia ordem. Retorna True se FiveM confirmou 2xx."""
        payload = {"action": action, **params}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                ok = 200 <= resp.status < 300
                with self._lock:
                    if not self._last_ok and ok:
                        print("[bridge] FiveM voltou a responder", flush=True)
                    self._last_ok = ok
                return ok
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            with self._lock:
                if self._last_ok:
                    print(f"[bridge] FiveM indisponível ({self._url}): {e}",
                          flush=True)
                self._last_ok = False
            return False

    def send_async(self, action: str, **params: Any) -> None:
        """Envia sem bloquear (thread daemon). Usado no loop de 30Hz do head tracker."""
        threading.Thread(
            target=self.send, args=(action,), kwargs=params, daemon=True
        ).start()

    def ping(self) -> bool:
        """Bate um ping pra saber se a resource tá viva."""
        return self.send("ping")


class CameraStream:
    """Envia atualizações de câmera do head tracker em throttle suave.

    O head tracker emite ~30 updates/s. A gente faz debounce: só envia se a
    última direção mudou o bastante OU se passou tempo demais sem enviar.
    """

    def __init__(self, bridge: FiveMBridge, min_interval_ms: int = 33,
                 min_delta: float = 0.02) -> None:
        self._bridge = bridge
        self._min_interval = min_interval_ms / 1000.0
        self._min_delta = min_delta
        self._last_x = 0.0
        self._last_y = 0.0
        self._last_t = 0.0
        self._started = False

    def set(self, x: float, y: float) -> None:
        now = time.monotonic()
        dx = abs(x - self._last_x)
        dy = abs(y - self._last_y)
        # Sempre envia se mudou relevante OU ficou quieto demais (GC de estado).
        if dx + dy < self._min_delta and (now - self._last_t) < self._min_interval:
            return
        self._last_x = x
        self._last_y = y
        self._last_t = now
        self._started = True
        self._bridge.send_async("camera_set", x=x, y=y)

    def stop(self) -> None:
        if self._started:
            self._bridge.send_async("camera_stop")
            self._started = False
            self._last_x = 0.0
            self._last_y = 0.0
