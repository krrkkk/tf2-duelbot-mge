from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import tarfile
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable
from contextlib import contextmanager

from .downloads import Cancelled, Progress, digest, fetch
from .steam import tf2_running, validate_tf_directory
from .steam import parse_vdf
from .storage import atomic_bytes, read_json, write_json


@contextmanager
def installation_lock(path: Path):

    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("An installation is already running") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def merge_spawn_config(existing: str, supplied: str, map_name: str) -> str:

    import re
    current = parse_vdf(existing)
    incoming = parse_vdf(supplied)
    if len(current) != 1 or not isinstance(next(iter(current.values())), dict):
        raise ValueError("Existing arena configuration cannot be merged safely")
    values = next(iter(current.values()))
    if map_name in values:
        return existing
    addition = next(iter(incoming.values())).get(map_name)
    if not isinstance(addition, dict):
        raise ValueError("The package has no configuration for the training map")

    def emit(key: str, value, depth: int = 1) -> list[str]:
        def quote(s):
            return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
        indent = "\t" * depth
        if isinstance(value, dict):
            output = [indent + quote(key), indent + "{"]
            for k, v in value.items():
                output.extend(emit(k, v, depth + 1))
            return output + [indent + "}"]
        return [indent + quote(key) + " " + quote(value)]

    closing = None
    depth = 0
    for match in re.finditer(r'//[^\n]*|"(?:\\.|[^"\\])*"|[{}]', existing):
        token = match.group()
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                closing = match.start()
    if closing is None:
        raise ValueError("Existing arena configuration has no closing section")
    return existing[:closing] + "\n" + "\n".join(emit(map_name, addition)) + "\n" + existing[closing:]


def archive_name(name: str) -> str:
    if "\\" in name or "\0" in name or ":" in name:
        raise ValueError("Unsafe archive filename")
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in ("..", ".") for p in path.parts):
        raise ValueError("Unsafe archive path")
    reserved = {"con", "prn", "aux", "nul", *("com" + str(n) for n in range(1, 10)), *("lpt" + str(n) for n in range(1, 10))}
    if any(p != p.rstrip(" .") or p.split(".", 1)[0].casefold() in reserved for p in path.parts):
        raise ValueError("Archive path uses a reserved Windows filename")
    return str(path)


def unpack(archive: Path, target: Path, cancel: threading.Event) -> None:
    total = 0
    seen: set[str] = set()

    def write(name: str, size: int, source) -> None:
        nonlocal total
        name = archive_name(name)
        if name.casefold() in seen:
            raise ValueError("Duplicate archive path")
        seen.add(name.casefold())
        total += size
        if size < 0 or size > 600 * 1024 * 1024 or total > 1400 * 1024 * 1024 or len(seen) > 30000:
            raise ValueError("Archive exceeds installation limits")
        if cancel.is_set():
            raise Cancelled("Installation cancelled")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            shutil.copyfileobj(source, output, 1024 * 1024)
        if destination.stat().st_size != size:
            raise ValueError("Incomplete archive entry")

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as contents:
            for info in contents.infolist():
                if info.is_dir():
                    archive_name(info.filename.rstrip("/"))
                    continue
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                    raise ValueError("Archive links and special files are not supported")
                with contents.open(info) as source:
                    write(info.filename, info.file_size, source)
    else:
        with tarfile.open(archive, "r:*") as contents:
            for info in contents:
                if info.isdir():
                    archive_name(info.name.rstrip("/"))
                    continue
                if not info.isfile():
                    raise ValueError("Archive links and special files are not supported")
                with contents.extractfile(info) as source:
                    write(info.name, info.size, source)


def _destination(root: Path, relative: str) -> Path:
    clean = archive_name(relative)
    path = root / clean

    cursor = root
    for part in PurePosixPath(clean).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"Installation path is a symlink: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Installation path escapes the game directory")
    if path.exists() and not path.is_file():
        raise ValueError(f"A directory occupies the destination: {relative}")
    return path


def dependency_files(directory: Path) -> dict[str, Path]:
    result = {}
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        parts = PurePosixPath(relative).parts
        if parts[0] not in ("addons", "cfg") or "scripting" in parts or path.suffix.casefold() in (".sp", ".inc", ".exe"):
            continue
        if "/logs/" in relative or "/data/" in relative:
            continue
        result["tf/" + relative] = path
    if not result:
        raise ValueError("The dependency package has no runtime files")
    return result


def payload_files(directory: Path, platform: str) -> tuple[dict[str, Path], dict]:
    manifest = read_json(directory / "MANIFEST.json")
    if not isinstance(manifest, dict) or manifest.get("name") != "mgebot duel" or manifest.get("platform", "").casefold() != platform:
        raise ValueError("Select the matching mgebot duel platform package")
    if manifest.get("source_code_included") or manifest.get("sourcemod_included"):
        raise ValueError("Unexpected plugin package format")
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) > 1000:
        raise ValueError("Invalid plugin package manifest")
    result = {}
    for name, spec in files.items():
        clean = archive_name(name)
        path = directory / clean
        if not path.is_file() or path.stat().st_size != spec["bytes"] or digest(path) != spec["sha256"]:
            raise ValueError(f"Plugin package verification failed: {name}")
        if name.startswith("tf/"):
            parts = PurePosixPath(name).parts
            if "scripting" in parts or path.suffix.casefold() in (".sq3", ".db", ".sqlite", ".sp", ".inc") or any(p in parts for p in ("data", "logs", "botduel_editor")):
                raise ValueError("Plugin package contains private or unsupported data")
            if path.name in ("admins.cfg", "admins_simple.ini", "databases.cfg"):
                raise ValueError("Plugin package must not replace user configuration")
            result[clean] = path
        elif name in ("linux-listen-fix/bin/linux64/libtier0_srv.so", "linux-listen-fix/bin/linux64/libvstdlib_srv.so"):
            result[name.removeprefix("linux-listen-fix/")] = path
    if "tf/addons/sourcemod/plugins/mge_botduel.smx" not in result or "tf/maps/mge_triumph_beta7_rc1.bsp" not in result:
        raise ValueError("Plugin binary or Triumph map is missing")
    return result, manifest


def local_config(password: str, port: int) -> bytes:
    if not password or any(c not in "0123456789abcdef" for c in password) or not 1024 <= port <= 65535:
        raise ValueError("Invalid generated local configuration")
    return ("con_logfile mgebot-console.log\nsv_lan 1\n" + f'rcon_password "{password}"\n'
            "mp_timelimit 0\nmp_autoteambalance 0\nmp_teams_unbalance_limit 0\n"
            "mp_idledealmethod 0\nmp_disable_respawn_times 1\nmp_waitingforplayers_time 0\nmp_waitingforplayers_restart 0\n"
            "mp_tournament 0\nmp_enableroundwaittime 0\nmp_waitingforplayers_cancel 1\n"
            "tf_weapon_criticals 0\nsm_botduel_stats 1\nsm_botduel_local 1\n"
            "sm plugins load mgebot_companion\n").encode()


class Installer:
    def __init__(self, app_data: Path, catalog: dict, process_check: Callable[[], bool] = tf2_running):
        self.app_data = app_data
        self.catalog = catalog
        self.process_check = process_check

    def install(self, tf_directory: Path, payload: Path, platform: str, progress: Progress,
                cancel: threading.Event, port: int = 27025, allow_running_local: bool = False) -> dict:
        tf = validate_tf_directory(tf_directory)
        if platform not in ("windows", "linux"):
            raise ValueError("Unsupported platform")
        if self.process_check() and not allow_running_local:
            raise RuntimeError("Close TF2 and local TF2 servers before installing")
        root = tf.parent
        self.app_data.mkdir(parents=True, exist_ok=True)
        with installation_lock(self.app_data / "install.lock"):
            for path in (self.app_data / "transactions").glob("*/journal.json"):
                old = read_json(path)
                if old.get("root") == str(root) and old.get("status") == "applying":
                    self._rollback(path.parent, old)
                    if old["status"] == "rollback_conflicts":
                        raise RuntimeError("A previous interrupted installation has user-modified files. See its recovery journal before continuing.")
            return self._install(tf, root, payload, platform, progress, cancel, port, allow_running_local)

    def _install(self, tf: Path, root: Path, payload: Path, platform: str,
                 progress: Progress, cancel: threading.Event, port: int, allow_running_local: bool = False) -> dict:
        journal = None
        connection_before = (self.app_data / "connection.json").read_bytes() if (self.app_data / "connection.json").is_file() else None
        connection_written = False
        try:
            with tempfile.TemporaryDirectory(prefix="install-", dir=self.app_data) as temporary:
                temporary = Path(temporary)
                combined: dict[str, Path] = {}
                preserve_existing: set[str] = set()
                for asset in self.catalog["dependencies"][platform]:
                    archive = fetch(asset, self.app_data / "cache", progress, cancel)
                    folder = temporary / asset["name"]
                    unpack(archive, folder, cancel)
                    files = dependency_files(folder)
                    combined.update(files)
                    preserve_existing.update(name for name in files if "/configs/" in name or name.startswith("tf/cfg/") or name in ("tf/addons/metamod.vdf", "tf/addons/metamod_x64.vdf", "tf/addons/metamod/metaplugins.ini"))
                progress("mgebot duel", 0, 0)
                own_folder = temporary / "plugin"
                unpack(payload, own_folder, cancel)
                own, metadata = payload_files(own_folder, platform)
                if metadata.get("version") != self.catalog["plugin_version"]:
                    raise ValueError("The plugin version does not match this launcher")
                if self.catalog.get("companion_version") and "tf/addons/sourcemod/plugins/mgebot_companion.smx" not in own:
                    raise ValueError("The complete release must include the local companion plugin")


                preserve_existing.add("tf/addons/sourcemod/configs/botduel_difficulty.cfg")
                preserve_existing.update(name for name in own if name.startswith("bin/"))
                combined.update(own)
                spawn_name = "tf/addons/sourcemod/configs/mgemod_spawns.cfg"
                old_spawn = _destination(root, spawn_name)
                if old_spawn.exists():
                    merged = merge_spawn_config(old_spawn.read_text(encoding="utf-8-sig"), own[spawn_name].read_text(encoding="utf-8-sig"), self.catalog["map"])
                    merged_file = temporary / "merged-spawns.cfg"
                    merged_file.write_text(merged, encoding="utf-8")
                    combined[spawn_name] = merged_file
                previous = read_json(self.app_data / "connection.json", {})
                password = previous.get("password") if previous.get("tf_directory") == str(tf) else None
                if not isinstance(password, str) or len(password) != 64 or any(c not in "0123456789abcdef" for c in password):
                    password = secrets.token_hex(32)
                generated = temporary / "mgebot-launcher.cfg"
                generated.write_bytes(local_config(password, port))
                combined["tf/cfg/mgebot-launcher.cfg"] = generated
                refresh = temporary / "mgebot-launcher-refresh.cfg"
                refresh.write_text("exec mgebot-launcher\nsm plugins reload mge_botduel\nsm plugins reload mgebot_companion\n")
                combined["tf/cfg/mgebot-launcher-refresh.cfg"] = refresh


                from .local import load_file_connection
                existing_bridge = load_file_connection(tf)
                installation = existing_bridge.installation if existing_bridge else uuid.uuid4().hex
                token = existing_bridge.token if existing_bridge else secrets.token_hex(32)
                bridge_config = temporary / "mgebot_companion.cfg"
                bridge_config.write_text('"MGBotCompanion"\n{\n    "version" "1"\n    "enabled" "1"\n'
                                         f'    "installation" "{installation}"\n    "token" "{token}"\n}}\n')
                combined["tf/addons/sourcemod/configs/mgebot_companion.cfg"] = bridge_config
                planned = []
                for name, source in sorted(combined.items()):
                    target = _destination(root, name)
                    if target.exists() and name in preserve_existing:
                        continue
                    source_hash = digest(source)
                    if target.is_file() and digest(target) == source_hash:
                        continue
                    planned.append({"path": name, "source": source, "sha256": source_hash, "previous_sha256": digest(target) if target.exists() else None,
                                    "previous_mode": stat.S_IMODE(target.stat().st_mode) if target.exists() else None})
                if cancel.is_set():
                    raise Cancelled("Installation cancelled")
                if self.process_check():
                    live_safe = {"tf/addons/sourcemod/plugins/mgebot_companion.smx", "tf/addons/sourcemod/plugins/mge_botduel.smx",
                                 "tf/addons/sourcemod/configs/mgebot_companion.cfg", "tf/cfg/mgebot-launcher.cfg", "tf/cfg/mgebot-launcher-refresh.cfg"}
                    if not allow_running_local or any(item["path"] not in live_safe for item in planned):
                        raise RuntimeError("Close TF2 to update its runtime components; your existing setup is preserved")
                free = shutil.disk_usage(root).free
                needed = sum(p["source"].stat().st_size * 2 for p in planned) + 32 * 1024 * 1024
                if free < needed:
                    raise OSError("Not enough free space for installation and rollback")
                transaction = self.app_data / "transactions" / uuid.uuid4().hex
                transaction.mkdir(parents=True)
                journal = {"version": 1, "root": str(root), "at": int(time.time()), "status": "applying", "files": []}


                for item in planned:
                    target = _destination(root, item["path"])
                    if item["previous_sha256"] is not None:
                        backup = transaction / "previous" / item["path"]
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                        if digest(backup) != item["previous_sha256"]:
                            raise RuntimeError("A game file changed during installation preparation")
                    record = {k: v for k, v in item.items() if k != "source"}
                    record["written"] = False
                    journal["files"].append(record)
                write_json(transaction / "journal.json", journal)
                for index, (item, record) in enumerate(zip(planned, journal["files"])):
                    if cancel.is_set():
                        raise Cancelled("Installation cancelled")
                    target = _destination(root, item["path"])
                    observed = digest(target) if target.exists() else None
                    if observed != item["previous_sha256"]:
                        raise RuntimeError("A game file changed during installation; its new contents were preserved")
                    atomic_bytes(target, item["source"].read_bytes(), 0o600 if target.name in ("mgebot-launcher.cfg", "mgebot_companion.cfg") else 0o644)
                    record["written"] = True
                    if (index + 1) % 32 == 0:
                        write_json(transaction / "journal.json", journal)
                    progress("Install", index + 1, len(planned))
                connection = {"tf_directory": str(tf), "port": port, "password": password,
                              "installation": installation, "transport": "file"}
                write_json(self.app_data / "connection.json", connection)
                connection_written = True
                journal["status"] = "complete"
                write_json(transaction / "journal.json", journal)
                result = {"version": metadata["version"], "platform": platform, "tf_directory": str(tf),
                          "transaction": str(transaction), "files_changed": len(planned), "installed_at": int(time.time())}
                write_json(self.app_data / "installation.json", result)
                return result
        except BaseException:
            if journal is not None:
                self._rollback(transaction, journal)
            if connection_written:
                if connection_before is None:
                    (self.app_data / "connection.json").unlink(missing_ok=True)
                else:
                    atomic_bytes(self.app_data / "connection.json", connection_before)
            raise

    @staticmethod
    def _rollback(transaction: Path, journal: dict) -> None:
        root = Path(journal["root"])
        conflicts = []
        for record in reversed(journal["files"]):
            target = _destination(root, record["path"])

            if not target.exists() or digest(target) != record["sha256"]:
                if record["written"]:
                    conflicts.append(record["path"])
                continue
            if record["previous_sha256"]:
                backup = transaction / "previous" / record["path"]
                if not backup.is_file() or digest(backup) != record["previous_sha256"]:
                    conflicts.append(record["path"])
                    continue
                atomic_bytes(target, backup.read_bytes(), record.get("previous_mode") or 0o600)
            else:
                target.unlink()
        journal["status"] = "rollback_conflicts" if conflicts else "rolled_back"
        journal["conflicts"] = conflicts
        write_json(transaction / "journal.json", journal)
