"""Executor de comandos via pynput (teclado + mouse).

Tipos suportados:
  - tap         : aperta e solta 1 tecla (duration_ms)
  - multi_tap   : aperta várias teclas simultâneas e solta (duration_ms)
  - hold_until  : aperta e SEGURA até outro comando liberar
  - release     : libera um hold_until em andamento
  - sequence    : lista de steps {action: tap|wait_ms, ...}

Mouse é suportado via strings especiais: "mouse_left", "mouse_right", "mouse_middle".
Tudo roda fora da thread do STT — cada comando vira uma thread daemon curta.
"""

import threading
import time
from typing import Dict, Optional

from pynput.keyboard import Controller as KbController, Key
from pynput.mouse import Button, Controller as MouseController

from commands.registry import Command, CommandRegistry


_KEY_ALIASES = {
    "space": Key.space,
    "spacebar": Key.space,
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "shift": Key.shift,
    "shift_l": Key.shift_l,
    "shift_r": Key.shift_r,
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "ctrl_l": Key.ctrl_l,
    "ctrl_r": Key.ctrl_r,
    "alt": Key.alt,
    "alt_l": Key.alt_l,
    "alt_r": Key.alt_r,
    "esc": Key.esc,
    "escape": Key.esc,
    "backspace": Key.backspace,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4, "f5": Key.f5,
    "f6": Key.f6, "f7": Key.f7, "f8": Key.f8, "f9": Key.f9, "f10": Key.f10,
    "f11": Key.f11, "f12": Key.f12,
}

_MOUSE_BUTTONS = {
    "mouse_left":   Button.left,
    "mouse_right":  Button.right,
    "mouse_middle": Button.middle,
}


def _resolve(key_str: str):
    """Retorna (kind, handle) — kind in {'mouse','key_special','key_char'}."""
    if not key_str:
        raise ValueError("tecla vazia")
    k = key_str.strip().lower()
    if k in _MOUSE_BUTTONS:
        return "mouse", _MOUSE_BUTTONS[k]
    if k in _KEY_ALIASES:
        return "key_special", _KEY_ALIASES[k]
    if len(key_str) == 1:
        return "key_char", key_str
    raise ValueError(f"tecla desconhecida: {key_str!r}")


class Executor:
    def __init__(self, registry: CommandRegistry, action_mode=None,
                 bridge=None) -> None:
        self._registry = registry
        self._kb = KbController()
        self._mouse = MouseController()
        # id -> (kind, handle) ainda pressionados (hold_until)
        self._holding: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._action_mode = action_mode
        self._bridge = bridge  # FiveMBridge ou None (modo pynput puro)

    def set_action_mode(self, action_mode) -> None:
        self._action_mode = action_mode

    def set_bridge(self, bridge) -> None:
        self._bridge = bridge

    # ------------------------------------------------------------------
    # Primitivas
    # ------------------------------------------------------------------
    def _press(self, kind: str, handle) -> None:
        if kind == "mouse":
            self._mouse.press(handle)
        else:
            self._kb.press(handle)

    def _release(self, kind: str, handle) -> None:
        if kind == "mouse":
            self._mouse.release(handle)
        else:
            self._kb.release(handle)

    def _tap(self, key_str: str, duration_ms: int) -> None:
        kind, handle = _resolve(key_str)
        self._press(kind, handle)
        time.sleep(max(1, duration_ms) / 1000.0)
        self._release(kind, handle)

    # ------------------------------------------------------------------
    # Dispatch por tipo
    # ------------------------------------------------------------------
    def execute(self, cmd: Command) -> bool:
        """Executa o comando em thread separada. Retorna True se iniciou ok."""
        try:
            if cmd.type == "tap":
                threading.Thread(
                    target=self._tap, args=(cmd.key, cmd.duration_ms), daemon=True
                ).start()
                return True

            if cmd.type == "multi_tap":
                threading.Thread(
                    target=self._run_multi_tap, args=(cmd.keys, cmd.duration_ms),
                    daemon=True,
                ).start()
                return True

            if cmd.type == "sequence":
                threading.Thread(
                    target=self._run_sequence, args=(cmd.steps,), daemon=True
                ).start()
                return True

            if cmd.type == "hold_until":
                if not cmd.key:
                    return False
                with self._lock:
                    if cmd.id in self._holding:
                        return True  # já está segurando — idempotente
                    kind, handle = _resolve(cmd.key)
                    self._press(kind, handle)
                    self._holding[cmd.id] = (kind, handle)
                print(f"[exec] HOLD {cmd.id} ({cmd.key})", flush=True)
                return True

            if cmd.type == "release":
                target = cmd.releases
                if not target:
                    return False
                with self._lock:
                    held = self._holding.pop(target, None)
                if held:
                    kind, handle = held
                    self._release(kind, handle)
                    print(f"[exec] RELEASE {target}", flush=True)
                    return True
                # Nada para liberar — ainda trata como sucesso silencioso
                return True

            if cmd.type == "enter_action_mode":
                if self._action_mode is None:
                    print("[exec] action_mode indisponível", flush=True)
                    return False
                threading.Thread(
                    target=self._action_mode.activate, daemon=True
                ).start()
                return True

            if cmd.type == "exit_action_mode":
                if self._action_mode is None:
                    return False
                threading.Thread(
                    target=self._action_mode.deactivate, daemon=True
                ).start()
                return True

            if cmd.type == "gaze_recalibrate":
                if self._action_mode is None:
                    return False
                threading.Thread(
                    target=self._action_mode.recalibrate, daemon=True
                ).start()
                return True

            if cmd.type == "engine":
                if self._bridge is None:
                    print("[exec] engine command sem bridge configurada", flush=True)
                    return False
                action = cmd.engine_action
                if not action:
                    print(f"[exec] engine sem action no comando {cmd.id}", flush=True)
                    return False
                params = dict(cmd.engine_params or {})
                self._bridge.send_async(action, **params)
                return True

            print(f"[exec] tipo desconhecido: {cmd.type}", flush=True)
            return False
        except Exception as e:
            print(f"[exec] erro executando {cmd.id}: {e}", flush=True)
            return False

    # ------------------------------------------------------------------
    def _run_multi_tap(self, keys, duration_ms: int) -> None:
        resolved = [_resolve(k) for k in keys]
        for kind, handle in resolved:
            self._press(kind, handle)
        time.sleep(max(1, duration_ms) / 1000.0)
        for kind, handle in reversed(resolved):
            self._release(kind, handle)

    def _run_sequence(self, steps) -> None:
        for step in steps:
            action = step.get("action")
            if action == "tap":
                self._tap(step.get("key"), int(step.get("duration_ms", 100)))
            elif action == "wait_ms":
                time.sleep(max(0, int(step.get("value", 0))) / 1000.0)
            elif action == "press":
                kind, handle = _resolve(step.get("key"))
                self._press(kind, handle)
            elif action == "release":
                kind, handle = _resolve(step.get("key"))
                self._release(kind, handle)
            else:
                print(f"[exec] step desconhecido: {action}", flush=True)

    def release_all_holds(self) -> None:
        """Libera todos os holds (usado no shutdown)."""
        with self._lock:
            holds = list(self._holding.items())
            self._holding.clear()
        for cid, (kind, handle) in holds:
            try:
                self._release(kind, handle)
                print(f"[exec] shutdown RELEASE {cid}", flush=True)
            except Exception:
                pass

    # Útil pra a UI testar uma tecla sem falar
    def test_command(self, cmd_id: str) -> bool:
        cmd = self._registry.get(cmd_id)
        if not cmd:
            return False
        return self.execute(cmd)
