from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass, field
from typing import Any


def _read(stream: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        part = stream.recv(count - len(data))
        if not part:
            raise ConnectionError("Local server closed the connection")
        data.extend(part)
    return bytes(data)


def _receive(stream: socket.socket) -> tuple[int, int, bytes]:
    size, = struct.unpack("<i", _read(stream, 4))
    if not 10 <= size <= 1024 * 1024:
        raise ValueError("Invalid server response length")
    data = _read(stream, size)
    if data[-2:] != b"\0\0":
        raise ValueError("Invalid server response terminator")
    request, kind = struct.unpack_from("<ii", data)
    return request, kind, data[8:-2]


def _send(stream: socket.socket, identifier: int, kind: int, body: bytes) -> None:
    data = struct.pack("<ii", identifier, kind) + body + b"\0\0"
    stream.sendall(struct.pack("<i", len(data)) + data)


@dataclass(frozen=True)
class LocalConnection:
    port: int
    password: str = field(repr=False)

    def execute(self, command: str) -> str:
        if not 1024 <= self.port <= 65535 or not self.password or len(self.password) > 128 or "\0" in self.password:
            raise ValueError("Invalid local connection configuration")
        body = command.encode("utf-8")
        if not body or len(body) > 4096 or any(c in command for c in "\0\n\r;"):
            raise ValueError("Invalid local command")
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as stream:
            _send(stream, 11, 3, self.password.encode())
            for _ in range(4):
                identifier, kind, _ = _receive(stream)
                if identifier == -1:
                    raise PermissionError("Local server password does not match the launcher configuration")
                if identifier == 11 and kind == 2:
                    break
            else:
                raise ConnectionError("Local server did not confirm authentication")
            _send(stream, 12, 2, body)
            _send(stream, 13, 0, b"")
            chunks: list[bytes] = []
            total = 0
            for _ in range(256):
                identifier, _, data = _receive(stream)
                if identifier == 13:
                    return b"".join(chunks).decode("utf-8", errors="strict")
                if identifier == 12:
                    total += len(data)
                    if total > 2 * 1024 * 1024:
                        raise ValueError("Local server response is too large")
                    chunks.append(data)
            raise ValueError("Local server response did not finish")

    def api(self, operation: str, *arguments: int | str) -> dict[str, Any]:
        if operation not in {"status", "players", "arenas", "snapshot", "apply", "start", "stop"}:
            raise ValueError("Unsupported local operation")
        values = []
        for argument in arguments:
            value = str(argument)
            if not value or len(value) > 64 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in value):
                raise ValueError("Invalid local operation argument")
            values.append(value)
        response = self.execute(" ".join(["sm_duel_local", operation, *values]))
        combined: dict[str, Any] = {"api": 1, "ok": True}
        fragmented = False
        for line in response.splitlines():
            if line.startswith("MGBOT_LOCAL "):
                result = json.loads(line.removeprefix("MGBOT_LOCAL "))
                if not isinstance(result, dict) or result.get("api") != 1:
                    raise ValueError("Unsupported plugin API version")
                if result.get("ok") is not True:
                    raise ValueError(str(result.get("error", "The plugin rejected this operation")))
                if "fragment" in result:
                    if not isinstance(result["fragment"], dict):
                        raise ValueError("Invalid plugin response fragment")
                    fragmented = True
                    combined.update(result["fragment"])
                    continue
                if "list" in result:
                    key = result["list"]
                    if key not in ("players", "arenas") or not isinstance(result.get("item"), dict):
                        raise ValueError("Invalid plugin response list")
                    fragmented = True
                    combined.setdefault(key, []).append(result["item"])
                    continue
                if result.get("done") is True:
                    if operation in ("players", "arenas"):
                        combined.setdefault(operation, [])
                    return combined
                combined.update(result)
                return combined
        if fragmented:
            raise ConnectionError("The local plugin response was incomplete")
        raise ConnectionError("The plugin's local control interface is unavailable. Install the matching plugin and launch a local training session.")
