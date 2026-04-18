"""Carrega e salva a lista de comandos do commands.json.

A UI web grava aqui. O matcher/executor lê daqui. Uma única fonte da verdade.
"""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional


@dataclass
class Command:
    id: str
    label: str
    description: str
    keywords: List[str]
    type: str
    # tap / hold_until
    key: Optional[str] = None
    duration_ms: int = 100
    # hold_until
    released_by: Optional[str] = None
    # release
    releases: Optional[str] = None
    # multi_tap
    keys: List[str] = field(default_factory=list)
    # sequence
    steps: List[dict] = field(default_factory=list)
    # engine
    engine_action: Optional[str] = None
    engine_params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Command":
        return cls(
            id=d["id"],
            label=d.get("label", d["id"]),
            description=d.get("description", ""),
            keywords=list(d.get("keywords", [])),
            type=d["type"],
            key=d.get("key"),
            duration_ms=int(d.get("duration_ms", 100)),
            released_by=d.get("released_by"),
            releases=d.get("releases"),
            keys=list(d.get("keys", [])),
            steps=list(d.get("steps", [])),
            engine_action=d.get("engine_action"),
            engine_params=dict(d.get("engine_params", {})),
        )

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "keywords": self.keywords,
            "type": self.type,
        }
        if self.type in ("tap", "hold_until"):
            out["key"] = self.key
        if self.type == "tap":
            out["duration_ms"] = self.duration_ms
        if self.type == "hold_until":
            out["released_by"] = self.released_by
        if self.type == "release":
            out["releases"] = self.releases
        if self.type == "multi_tap":
            out["keys"] = self.keys
            out["duration_ms"] = self.duration_ms
        if self.type == "sequence":
            out["steps"] = self.steps
        if self.type == "engine":
            out["engine_action"] = self.engine_action
            if self.engine_params:
                out["engine_params"] = self.engine_params
        return out


class CommandRegistry:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._commands: List[Command] = []
        self._listeners: List[Callable[[List[Command]], None]] = []
        self.reload()

    @property
    def path(self) -> Path:
        return self._path

    def reload(self) -> List[Command]:
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._commands = [Command.from_dict(c) for c in data.get("commands", [])]
            snapshot = list(self._commands)
        for fn in list(self._listeners):
            try: fn(snapshot)
            except Exception as e:
                print(f"[registry] listener erro: {e}", flush=True)
        return snapshot

    def all(self) -> List[Command]:
        with self._lock:
            return list(self._commands)

    def get(self, cmd_id: str) -> Optional[Command]:
        with self._lock:
            for c in self._commands:
                if c.id == cmd_id:
                    return c
        return None

    def save(self, commands: List[dict]) -> List[Command]:
        parsed = [Command.from_dict(c) for c in commands]
        payload = {"commands": [c.to_dict() for c in parsed]}
        with self._lock:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._commands = parsed
            snapshot = list(self._commands)
        for fn in list(self._listeners):
            try: fn(snapshot)
            except Exception as e:
                print(f"[registry] listener erro: {e}", flush=True)
        return snapshot

    def on_change(self, fn: Callable[[List[Command]], None]) -> None:
        self._listeners.append(fn)
