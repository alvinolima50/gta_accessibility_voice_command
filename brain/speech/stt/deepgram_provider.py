"""STT streaming via Deepgram Nova-2.

Mantém keepalive e reconecta se o websocket cair.
Versão copiada do Bot_GTA, sem alterações no protocolo.
"""

import threading
import time
from typing import Callable

from deepgram import DeepgramClient, LiveTranscriptionEvents

try:
    from deepgram import LiveOptions
except ImportError:
    try:
        from deepgram.clients.live.v1 import LiveOptions
    except ImportError:
        LiveOptions = None

from config import Config
from speech.stt.base import STTProvider, STTSession


class _DGSession(STTSession):
    def __init__(self, client, sr: int, on_final: Callable[[str], None], label: str = "stt") -> None:
        self._client = client
        self._sr = sr
        self._on_final = on_final
        self._label = label
        self._lock = threading.Lock()
        self._conn = None
        self._closed = False
        self._reconnecting = False
        self._connect()
        threading.Thread(target=self._keepalive_loop, daemon=True).start()

    def _connect(self) -> None:
        with self._lock:
            if self._conn is not None:
                try: self._conn.finish()
                except Exception: pass
                self._conn = None

            conn = self._client.listen.websocket.v("1")

            def _on_transcript(_, result, **kwargs):
                try:
                    alt = result.channel.alternatives[0]
                    text = (alt.transcript or "").strip()
                    is_final = getattr(result, "is_final", False)
                    if text:
                        tag = "FINAL" if is_final else "parcial"
                        print(f"[{self._label}] {tag}: {text!r}", flush=True)
                    if is_final and text:
                        self._on_final(text)
                except Exception as e:
                    print(f"[{self._label}] transcript err: {e}", flush=True)

            def _on_close(_, **kwargs):
                if self._closed or self._reconnecting:
                    return
                print("[stt] deepgram fechou — reconectando...", flush=True)
                self._reconnecting = True
                threading.Thread(target=self._reconnect_soon, daemon=True).start()

            def _on_error(_, error, **kwargs):
                print(f"[stt] deepgram error: {error}", flush=True)

            conn.on(LiveTranscriptionEvents.Transcript, _on_transcript)
            conn.on(LiveTranscriptionEvents.Close, _on_close)
            conn.on(LiveTranscriptionEvents.Error, _on_error)

            opts_dict = {
                "model": "nova-2",
                "language": Config.DEEPGRAM_LANGUAGE,
                "encoding": "linear16",
                "sample_rate": self._sr,
                "channels": 1,
                "punctuate": True,
                "smart_format": True,
                "endpointing": 300,
                "interim_results": True,
            }
            opts = LiveOptions(**opts_dict) if LiveOptions else opts_dict
            started = conn.start(opts)
            if not started:
                raise RuntimeError("Falha ao abrir conexão Deepgram")
            self._conn = conn
            print(f"[{self._label}] deepgram conectado", flush=True)

    def _reconnect_soon(self) -> None:
        time.sleep(1)
        try:
            self._connect()
        except Exception as e:
            print(f"[stt] reconnect falhou: {e}", flush=True)
        finally:
            self._reconnecting = False

    def _keepalive_loop(self) -> None:
        while not self._closed:
            time.sleep(5)
            try:
                if self._conn is not None:
                    self._conn.send(b'{"type":"KeepAlive"}')
            except Exception:
                pass

    def feed(self, pcm_bytes: bytes) -> None:
        try:
            if self._conn is not None:
                self._conn.send(pcm_bytes)
        except Exception as e:
            print(f"[stt] feed error: {e}", flush=True)

    def close(self) -> None:
        self._closed = True
        try:
            if self._conn is not None:
                self._conn.finish()
        except Exception:
            pass


class DeepgramSTT(STTProvider):
    def __init__(self, sample_rate: int = 16000) -> None:
        self._sr = sample_rate
        self._client = DeepgramClient(Config.DEEPGRAM_API_KEY)

    def open_session(self, on_final: Callable[[str], None], label: str = "stt") -> STTSession:
        return _DGSession(self._client, self._sr, on_final, label=label)
