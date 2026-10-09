from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def data_directory() -> Path:
    override = os.environ.get("MGEBOT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "mgebot-duel"


def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    if path.stat().st_size > 2_000_000:
        raise ValueError("Local settings file is too large")
    return json.loads(path.read_text(encoding="utf-8-sig"))
