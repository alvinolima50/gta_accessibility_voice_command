"""Beep sutil de confirmação.

Usa winsound no Windows (sem dependência extra). Em outros sistemas,
cai num print — o projeto é Windows-first mas não quebra rodando fora.
Chama em thread separada pra não bloquear o pipeline de voz.
"""

import threading

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False


def beep(freq_hz: int = 880, duration_ms: int = 80) -> None:
    def _run():
        if _HAS_WINSOUND:
            try:
                winsound.Beep(int(freq_hz), int(duration_ms))
                return
            except Exception as e:
                print(f"[beep] winsound falhou: {e}", flush=True)
        print("[beep] *bip*", flush=True)

    threading.Thread(target=_run, daemon=True).start()
