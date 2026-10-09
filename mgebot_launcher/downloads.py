from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

Progress = Callable[[str, int, int], None]


class Cancelled(Exception):
    pass


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fetch(asset: dict, cache: Path, progress: Progress, cancel: threading.Event) -> Path:
    expected = asset.get("sha256", "")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("The download has no pinned SHA-256")
    url = asset["url"]
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in {"github.com", "www.python.org", "files.pythonhosted.org", "archive.ubuntu.com"}:
        raise ValueError("Unsupported download origin")
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / (expected + ".download")
    if destination.is_file() and digest(destination) == expected:
        return destination
    fd, temporary = tempfile.mkstemp(prefix="download-", dir=cache)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "mgebot-duel-launcher/0.1"})
        with os.fdopen(fd, "wb") as stream, urllib.request.urlopen(request, timeout=20) as response:
            if urllib.parse.urlsplit(response.url).scheme != "https":
                raise ValueError("Insecure download redirect")
            total = int(asset.get("size", 0))
            written = 0
            while True:
                if cancel.is_set():
                    raise Cancelled("Download cancelled")
                block = response.read(256 * 1024)
                if not block:
                    break
                written += len(block)
                if written > 600 * 1024 * 1024 or (total and written > total):
                    raise ValueError("Unexpected download size")
                stream.write(block)
                progress(asset.get("name", "Download"), written, total)
            stream.flush()
            os.fsync(stream.fileno())
        if digest(Path(temporary)) != expected:
            raise ValueError("Downloaded file failed SHA-256 verification")
        if total and written != total:
            raise ValueError("Downloaded file is incomplete")
        os.replace(temporary, destination)
        return destination
    finally:
        Path(temporary).unlink(missing_ok=True)
