"""Captura do microfone padrão do sistema.

PCM 16-bit @ 16kHz mono, empurrado em chunks de 50ms pra um callback.
Versão simplificada do projeto Bot_GTA — sem loopback, sem resolver.
"""

import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd


SAMPLE_RATE   = 16000
CHUNK_MS      = 50
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000


def _float_to_pcm16(arr: np.ndarray) -> bytes:
    arr = np.clip(arr, -1.0, 1.0)
    return (arr * 32767.0).astype(np.int16).tobytes()


def _rms_dbfs(arr: np.ndarray) -> float:
    if arr.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
    if rms < 1e-6:
        return -120.0
    return 20.0 * np.log10(rms)


class MicCapture:
    def __init__(self, on_chunk: Callable[[bytes], None], label: str = "mic") -> None:
        self._on_chunk = on_chunk
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._label = label
        self._last_db_log = 0.0
        self._peak_db = -120.0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        def cb(indata, frames, time_info, status):
            if self._stop.is_set():
                raise sd.CallbackStop
            mono = (indata[:, 0] if indata.ndim > 1 else indata).astype(np.float32)
            db = _rms_dbfs(mono)
            self._peak_db = max(self._peak_db, db)
            now = time.time()
            if now - self._last_db_log >= 5.0:
                print(f"[{self._label}] pico últimos 5s = {self._peak_db:.1f} dBFS", flush=True)
                self._peak_db = -120.0
                self._last_db_log = now
            self._on_chunk(_float_to_pcm16(mono))

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=CHUNK_SAMPLES, callback=cb):
            self._stop.wait()

    def stop(self) -> None:
        self._stop.set()
