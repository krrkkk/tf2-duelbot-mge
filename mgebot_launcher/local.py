from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .rcon import LocalConnection
from .storage import atomic_bytes, read_json


class LocalNotReady(ConnectionError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


@dataclass
class FileConnection:
    tf_directory: Path
    installation: str
    token: str = field(repr=False)
    timeout: float = 4.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def directory(self) -> Path:
        return self.tf_directory / "addons/sourcemod/data/mgebot_companion"

    def heartbeat(self) -> dict:
        path = self.directory / "heartbeat.json"
        if self.directory.is_symlink() or not self.directory.resolve().is_relative_to(self.tf_directory.resolve()):
            raise ValueError("The local connection directory is outside this TF2 installation")
        try:
            value = read_json(path)
        except (OSError, ValueError):
            value = None
        if not isinstance(value, dict) or value.get("bridge") != 1:
            raise LocalNotReady("waiting_plugin", "Waiting for the local training plugin")
        if value.get("installation") != self.installation:
            raise LocalNotReady("wrong_installation", "The running game belongs to a different launcher installation")
        if not value.get("listen") or not value.get("insecure"):
            raise LocalNotReady("secure_game", "Local training requires TF2 started with -insecure")
        if abs(time.time() - float(value.get("at", 0))) > 5:
            raise LocalNotReady("waiting_map", "Waiting for a local training map")
        if value.get("plugin_loaded") is not True:
            raise LocalNotReady("missing_plugin", "mgebot duel is not loaded in the running game")
        if not re.fullmatch(r"[a-f0-9]{1,8}-[a-f0-9]{1,8}", str(value.get("epoch", ""))):
            raise LocalNotReady("waiting_plugin", "The local game identity is incomplete")
        return value

    def api(self, operation: str, *arguments: int | str) -> dict:

        return LocalConnection.api(self, operation, *arguments)

    def execute(self, command: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{32}", self.installation) or not re.fullmatch(r"[a-f0-9]{64}", self.token):
            raise ValueError("The local installation identity is invalid")
        parts = command.split()
        if len(parts) < 2 or parts[0] != "sm_duel_local":
            raise ValueError("Only the typed local training API is available")
        operation, arguments = parts[1], parts[2:]
        sizes = {"status": 0, "players": 0, "arenas": 0, "snapshot": 1, "stop": 1, "apply": 2, "start": 3}
        if operation not in sizes or len(arguments) != sizes[operation]:
            raise ValueError("Invalid local operation")
        with self._lock:
            heartbeat = self.heartbeat()
            identifier = uuid.uuid4().hex
            values = {"version": "1", "id": identifier, "token": self.token,
                      "installation": self.installation, "epoch": heartbeat["epoch"], "created": str(int(time.time())), "operation": operation}
            if arguments:
                if not arguments[0].isdigit() or int(arguments[0]) <= 0:
                    raise ValueError("Invalid local player")
                values["userid"] = arguments[0]
            if operation == "start":
                if not arguments[1].isdigit() or not 1 <= int(arguments[1]) <= 256:
                    raise ValueError("Invalid arena")
                values["arena"] = arguments[1]
            if operation in ("apply", "start"):
                if not re.fullmatch(r"[a-f0-9]{32}", arguments[-1]):
                    raise ValueError("Invalid preset identifier")
                values["preset"] = arguments[-1]
            request = self.directory / "request.cfg"
            reply = self.directory / f"reply-{identifier}.jsonl"
            document = '"MGBotRequest"\n{\n' + "".join(f'    "{key}" "{value}"\n' for key, value in values.items()) + "}\n"
            atomic_bytes(request, document.encode())
            deadline = time.monotonic() + self.timeout
            try:
                while time.monotonic() < deadline:
                    if reply.is_file():
                        if reply.stat().st_size > 131072:
                            raise ValueError("The local plugin response is too large")
                        text = reply.read_text(encoding="utf-8-sig")
                        first = next((line for line in text.splitlines() if line.startswith("MGBOT_LOCAL ")), "")
                        try:
                            stamp = json.loads(first.removeprefix("MGBOT_LOCAL "))["fragment"]
                        except (ValueError, KeyError):
                            raise ConnectionError("The local plugin response is incomplete") from None
                        if stamp.get("installation") != self.installation or stamp.get("epoch") != heartbeat.get("epoch"):
                            raise LocalNotReady("map_changed", "The local map changed; reconnecting")
                        return text
                    time.sleep(0.04)
                raise LocalNotReady("plugin_timeout", "The local plugin did not answer. The game may be loading or paused.")
            finally:
                reply.unlink(missing_ok=True)

                try:
                    if request.exists() and f'"id" "{identifier}"' in request.read_text():
                        request.unlink()
                except OSError:
                    pass


def load_file_connection(tf_directory: Path) -> FileConnection | None:

    from .steam import parse_vdf
    config = tf_directory / "addons/sourcemod/configs/mgebot_companion.cfg"
    if not config.is_file() or config.stat().st_size > 2048:
        return None
    try:
        values = parse_vdf(config.read_text(encoding="utf-8-sig"))["MGBotCompanion"]
        if values.get("version") != "1" or values.get("enabled") != "1":
            return None
        installation, token = values["installation"], values["token"]
        if re.fullmatch(r"[a-f0-9]{32}", installation) and re.fullmatch(r"[a-f0-9]{64}", token):
            return FileConnection(tf_directory, installation, token)
    except (ValueError, OSError, KeyError):
        pass
    return None
