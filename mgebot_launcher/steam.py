from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
import json
import time

from .storage import atomic_bytes


def parse_vdf(text: str) -> dict:

    token = re.compile(r'\s+|//[^\n]*|"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)')
    tokens = []
    position = 0
    for match in token.finditer(text.lstrip("\ufeff")):
        if match.start() != position:
            raise ValueError("Invalid Steam manifest")
        position = match.end()
        if match.group(1) is not None:
            tokens.append(("text", re.sub(r'\\([\\"])', r'\1', match.group(1))))
        elif match.group(2):
            tokens.append(("brace", match.group(2)))
        elif match.group(3):
            tokens.append(("text", match.group(3)))
    if position != len(text.lstrip("\ufeff")):
        raise ValueError("Incomplete Steam manifest")
    cursor = 0

    def group(nested: bool = False) -> dict:
        nonlocal cursor
        result = {}
        while cursor < len(tokens):
            kind, key = tokens[cursor]
            cursor += 1
            if kind == "brace" and key == "}" and nested:
                return result
            if kind != "text" or cursor >= len(tokens):
                raise ValueError("Invalid Steam manifest entry")
            kind, value = tokens[cursor]
            cursor += 1
            if kind == "brace" and value == "{":
                value = group(True)
            elif kind != "text":
                raise ValueError("Invalid Steam manifest value")
            result[key] = value
        if nested:
            raise ValueError("Unclosed Steam manifest section")
        return result

    return group()


def steam_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        import winreg
        for hive, key, value in [(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")]:
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(Path(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                pass
        roots += [Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam"]
    else:
        roots += [Path.home() / p for p in (".steam/steam", ".local/share/Steam", ".var/app/com.valvesoftware.Steam/.local/share/Steam")]
    return list(dict.fromkeys(p.resolve() for p in roots if p.is_dir()))


def validate_tf_directory(path: Path) -> Path:
    path = path.expanduser().resolve()
    if (path / "tf/gameinfo.txt").is_file():
        path /= "tf"
    info = path / "gameinfo.txt"
    if path.name.casefold() != "tf" or not info.is_file():
        raise ValueError("Select Team Fortress 2 or its tf directory")
    content = info.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"Team\s+Fortress|SteamAppId[\s\"]+440", content, re.IGNORECASE):
        raise ValueError("The selected gameinfo.txt does not identify Team Fortress 2")
    return path


def find_tf_directories(roots: list[Path] | None = None) -> list[Path]:
    libraries = list(roots if roots is not None else steam_roots())
    for root in list(libraries):
        manifest = root / "steamapps/libraryfolders.vdf"
        if not manifest.is_file():
            continue
        try:
            data = parse_vdf(manifest.read_text(encoding="utf-8-sig"))
            folder = next((v for k, v in data.items() if k.casefold() == "libraryfolders"), {})
            for key, value in folder.items():
                if key.isdigit():
                    entry = value.get("path") if isinstance(value, dict) else value
                    if isinstance(entry, str):
                        libraries.append(Path(entry))
        except (OSError, ValueError, AttributeError):
            continue
    result = []
    for library in dict.fromkeys(libraries):
        manifest = library / "steamapps/appmanifest_440.acf"
        directory = "Team Fortress 2"
        if manifest.is_file():
            try:
                state = parse_vdf(manifest.read_text(encoding="utf-8-sig")).get("AppState", {})
                if str(state.get("appid", "")) == "440":
                    directory = state.get("installdir", directory)
            except (OSError, ValueError, AttributeError):
                continue
        if not isinstance(directory, str) or any(c in directory for c in "/\\") or directory in (".", ".."):
            continue
        try:
            result.append(validate_tf_directory(library / "steamapps/common" / directory))
        except (ValueError, OSError):
            continue
    return list(dict.fromkeys(result))


def tf2_running() -> bool:
    names = {"tf_win64.exe", "tf.exe", "hl2.exe", "srcds.exe", "srcds_win64.exe", "tf_linux64", "hl2_linux", "srcds_linux64", "srcds_linux"}
    if sys.platform == "win32":
        result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise OSError("Could not inspect running game processes")
        return any(row and row[0].casefold() in names for row in csv.reader(io.StringIO(result.stdout)))
    for process in Path("/proc").glob("[0-9]*/comm"):
        try:
            if process.read_text().strip().casefold() in names:
                return True
        except OSError:
            pass
    return False


@dataclass(frozen=True)
class GameProcess:
    pid: int
    executable: str
    command_line: str
    insecure: bool | None
    tf_directory: Path | None


def _process_game_directory(executable: str) -> Path | None:
    if not executable:
        return None
    for parent in list(Path(executable).parents)[:4]:
        if (parent / "tf/gameinfo.txt").is_file():
            return (parent / "tf").resolve()
    return None


def running_games() -> list[GameProcess]:

    names = {"tf_win64.exe", "tf.exe", "hl2.exe", "tf_linux64", "hl2_linux"}
    result = []
    if sys.platform == "win32":
        query = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-CimInstance Win32_Process -Filter \"Name='tf_win64.exe' OR Name='tf.exe' OR Name='hl2.exe'\" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        try:
            process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", query],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if process.returncode:
                raise OSError("Windows could not read the TF2 process information")
            rows = json.loads(process.stdout.lstrip("\ufeff")) if process.stdout.strip() else []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                executable = row.get("ExecutablePath") or ""
                command = row.get("CommandLine") or ""
                insecure = bool(re.search(r"(?:^|\s)-insecure(?:\s|$)", command, re.I)) if command else None
                result.append(GameProcess(int(row["ProcessId"]), executable, command, insecure, _process_game_directory(executable)))
        except (OSError, ValueError, subprocess.TimeoutExpired):

            process = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for row in csv.reader(io.StringIO(process.stdout)):
                if len(row) > 1 and row[0].casefold() in names and row[1].isdigit():
                    result.append(GameProcess(int(row[1]), "", "", None, None))
    else:
        for entry in Path("/proc").glob("[0-9]*"):
            try:
                name = (entry / "comm").read_text().strip().casefold()
                if name not in names:
                    continue
                arguments = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
                executable = str((entry / "exe").resolve())
                result.append(GameProcess(int(entry.name), executable, " ".join(arguments),
                                          "-insecure" in arguments, _process_game_directory(executable)))
            except (OSError, ValueError):
                continue
    return result


def launch_training(port: int, map_name: str = "mge_triumph_beta7_rc1", tf_directory: Path | None = None,
                    existing: GameProcess | None = None, bootstrap_only: bool = False, refresh: bool = False) -> None:
    if not 1024 <= port <= 65535 or not re.fullmatch(r"[a-z0-9_]+", map_name):
        raise ValueError("Invalid local launch configuration")
    if tf_directory is not None:
        marker = tf_directory / "addons/sourcemod/data/mgebot_companion/launch.cfg"
        if marker.parent.is_symlink() or not marker.parent.resolve().is_relative_to(tf_directory.resolve()):
            raise ValueError("Local training files must stay inside the selected TF2 folder")
        atomic_bytes(marker, ('"MGBotLaunch"\n{\n    "created" "'+str(int(time.time()))+'"\n}\n').encode())
    if existing is not None:
        if existing.insecure is not True:
            raise RuntimeError("Restart TF2 with -insecure to enable local training")
        if tf_directory and existing.tf_directory != tf_directory.resolve():
            raise RuntimeError("The running TF2 uses a different game folder")
        if not existing.executable:
            raise RuntimeError("The running TF2 executable could not be identified")
        arguments = [existing.executable, "-hijack", "-console"]
        if not bootstrap_only:
            arguments += ["+map", map_name]
        arguments += ["+exec", "mgebot-launcher-refresh" if refresh else "mgebot-launcher"]
        subprocess.Popen(arguments, close_fds=True, env=_steam_environment())
        return
    if running_games():
        raise RuntimeError("TF2 started while preparing the launch; reconnect to that instance")
    executable = None
    if sys.platform == "win32":
        executable = next((str(p / "steam.exe") for p in steam_roots() if (p / "steam.exe").is_file()), None)
    else:
        executable = shutil.which("steam")
    args = ["-applaunch", "440", "-insecure", "-console", "-condebug", "-ip", "127.0.0.1", "-port", str(port),
            "+map", map_name, "+exec", "mgebot-launcher"]
    environment = _steam_environment()
    if executable:
        subprocess.Popen([executable, *args], close_fds=True, env=environment)
    elif sys.platform != "win32" and shutil.which("flatpak"):
        subprocess.Popen(["flatpak", "run", "com.valvesoftware.Steam", *args], close_fds=True, env=environment)
    else:
        raise FileNotFoundError("Steam was not found. Open Steam once, then try again.")


def _steam_environment() -> dict:
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        environment.pop(key, None)
    if "MGEBOT_ORIGINAL_LD_LIBRARY_PATH" in environment:
        original = environment.pop("MGEBOT_ORIGINAL_LD_LIBRARY_PATH")
        if original:
            environment["LD_LIBRARY_PATH"] = original
        else:
            environment.pop("LD_LIBRARY_PATH", None)
    return environment
