"""Servidor web local pra configurar os comandos.

Endpoints:
  GET  /                    -> index.html
  GET  /api/commands        -> lista de comandos (json)
  POST /api/commands        -> salva lista inteira (body = {"commands": [...]})
  POST /api/test/{cmd_id}   -> dispara o comando agora (pra testar tecla)
  POST /api/reload          -> recarrega commands.json do disco
"""

from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from commands.executor import Executor
from commands.registry import CommandRegistry


class CommandsPayload(BaseModel):
    commands: List[dict[str, Any]]


_STATIC_DIR = Path(__file__).parent / "static"


def build_app(registry: CommandRegistry, executor: Executor) -> FastAPI:
    app = FastAPI(title="Acessibilidade GTA — Config")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(_STATIC_DIR / "index.html"))

    @app.get("/api/commands")
    def get_commands():
        return {"commands": [c.to_dict() for c in registry.all()]}

    @app.post("/api/commands")
    def save_commands(payload: CommandsPayload):
        try:
            saved = registry.save(payload.commands)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Falha ao salvar: {e}")
        return {"ok": True, "count": len(saved)}

    @app.post("/api/test/{cmd_id}")
    def test_command(cmd_id: str):
        ok = executor.test_command(cmd_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"comando {cmd_id} não encontrado")
        return {"ok": True}

    @app.post("/api/reload")
    def reload_commands():
        cmds = registry.reload()
        return {"ok": True, "count": len(cmds)}

    return app


def start_web_server(registry: CommandRegistry, executor: Executor,
                     host: str, port: int) -> None:
    app = build_app(registry, executor)
    # log_level=warning pra não poluir o console (o log de match do STT importa mais)
    uvicorn.run(app, host=host, port=port, log_level="warning")
