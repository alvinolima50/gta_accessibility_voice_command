"""Configuração central. Lê .env uma vez."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / "brain" / ".env")
load_dotenv(_ROOT / ".env")


class Config:
    DEEPGRAM_API_KEY  = os.getenv("DEEPGRAM_API_KEY", "")
    DEEPGRAM_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", "pt-BR")

    COMMANDS_JSON = Path(os.getenv("COMMANDS_JSON", _ROOT / "config" / "commands.json"))

    WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT = int(os.getenv("WEB_PORT", "8765"))

    BEEP_FREQ_HZ = int(os.getenv("BEEP_FREQ_HZ", "880"))
    BEEP_MS      = int(os.getenv("BEEP_MS", "80"))

    # Eye tracker: índice da webcam (varia de máquina pra máquina)
    GAZE_CAM_INDEX = int(os.getenv("GAZE_CAM_INDEX", "0"))

    # FiveM: endpoint HTTP do servidor onde a resource acessibilidade_gta está rodando.
    # Default é localhost:30120 — padrão do artifact do FiveM server.
    FIVEM_BASE_URL = os.getenv("FIVEM_BASE_URL", "http://127.0.0.1:30120")

    # Janela em que uma mesma transcrição é ignorada após disparar um comando
    # (evita duplicar quando o STT entrega parciais repetidos).
    DEBOUNCE_MS = int(os.getenv("DEBOUNCE_MS", "800"))

    @classmethod
    def require(cls) -> None:
        if not cls.DEEPGRAM_API_KEY:
            raise RuntimeError(
                "DEEPGRAM_API_KEY ausente. Crie brain/.env com DEEPGRAM_API_KEY=..."
            )
