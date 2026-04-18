"""Ponto de entrada do assistente de voz de acessibilidade.

Fluxo:
  Mic -> Deepgram streaming -> transcript final
  -> Matcher (keyword -> command)
  -> Executor (pynput -> teclas/mouse do sistema)
  -> Beep de confirmação.

Paralelo: servidor web local em /web pra editar commands.json.
"""

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import sys
import threading
import time
from pathlib import Path

# Permite importar o pacote gaze_tracker que mora ao lado de brain/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audio.beep import beep
from bridge.fivem import FiveMBridge
from commands.executor import Executor
from commands.matcher import Matcher
from commands.registry import CommandRegistry
from config import Config
from modes.action_mode import ActionMode
from speech.capture import MicCapture
from speech.stt.deepgram_provider import DeepgramSTT
from web.app import start_web_server


class VoiceApp:
    def __init__(self) -> None:
        Config.require()
        self.registry = CommandRegistry(Config.COMMANDS_JSON)
        self.bridge = FiveMBridge(base_url=Config.FIVEM_BASE_URL)
        self.action_mode = ActionMode(
            camera_index=Config.GAZE_CAM_INDEX,
            bridge=self.bridge,
            on_status=lambda s: print(f"[action_mode] {s}", flush=True),
        )
        self.executor = Executor(self.registry, action_mode=self.action_mode,
                                 bridge=self.bridge)
        self.matcher = Matcher(self.registry.all())
        self.registry.on_change(lambda cmds: self.matcher.update(cmds))

        self.stt = DeepgramSTT(sample_rate=16000)
        self._session = self.stt.open_session(self._on_transcript, label="mic-stt")

        self._mic_chunks = 0
        def _feed(pcm: bytes) -> None:
            self._mic_chunks += 1
            self._session.feed(pcm)
        self.mic = MicCapture(on_chunk=_feed, label="mic")

        self._last_command_ts = 0.0
        self._last_command_id: str | None = None

    def _on_transcript(self, text: str) -> None:
        now = time.time()
        if (now - self._last_command_ts) * 1000 < Config.DEBOUNCE_MS:
            return  # dentro da janela de debounce — ignora
        # Normaliza pra logar a forma "limpa" (sem maiúsculas, pontos, acentos)
        from commands.matcher import _normalize
        norm = _normalize(text)
        result = self.matcher.match(text)
        if not result:
            # Só loga "no match" se houve alguma keyword candidata no texto —
            # reduz ruído pra fala casual.
            return
        cmd, kw = result
        print(f"[match] {cmd.id}  <-  keyword={kw!r}  norm={norm!r}  raw={text!r}",
              flush=True)
        ok = self.executor.execute(cmd)
        if ok:
            self._last_command_ts = now
            self._last_command_id = cmd.id
            beep(Config.BEEP_FREQ_HZ, Config.BEEP_MS)

    def start(self) -> None:
        # Web server em thread separada (FastAPI/uvicorn já não bloqueia o main
        # porque a gente inicia em daemon thread).
        threading.Thread(
            target=start_web_server,
            args=(self.registry, self.executor, Config.WEB_HOST, Config.WEB_PORT),
            daemon=True,
        ).start()

        print(f"[main] web UI em http://{Config.WEB_HOST}:{Config.WEB_PORT}", flush=True)
        print("[main] iniciando microfone...", flush=True)
        try:
            self.mic.start()
            print("[main] mic OK", flush=True)
        except Exception as e:
            print(f"[main] mic FAIL: {e}", flush=True)
            return

        print("[main] pronto — fale um comando. Ctrl+C pra sair.", flush=True)
        try:
            while True:
                time.sleep(10)
                print(f"[main] ...vivo (mic_chunks={self._mic_chunks})", flush=True)
        except KeyboardInterrupt:
            print("[main] encerrando — liberando holds", flush=True)
            self.executor.release_all_holds()
            self.action_mode.deactivate()


if __name__ == "__main__":
    VoiceApp().start()
