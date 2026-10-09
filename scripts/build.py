#!/usr/bin/env python3


from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mgebot_launcher import __version__
from mgebot_launcher.downloads import digest, fetch
from package import source_files
from public_source import public_bytes


def extract_zip(path: Path, destination: Path):
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            target = destination / info.filename
            if not target.resolve().is_relative_to(destination.resolve()) or "\\" in info.filename:
                raise ValueError("Unsafe pinned archive path")
        archive.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("windows", "linux"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--runtime-only", action="store_true", help="Prepare a developer preview, not a distributable release")
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Output directory is not empty; use a new build directory")
    if not args.runtime_only and (not args.payload or not args.payload.is_file()):
        raise SystemExit("A published, matching plugin platform archive is required")
    lock = json.loads((ROOT / "build-lock.json").read_text())
    runtime = lock["runtimes"][args.platform]
    assets = [runtime, *lock["wheels"][args.platform]]
    if args.platform == "linux":
        assets.append(lock["linux_extra"])
    cancellation = threading.Event()
    args.cache.mkdir(parents=True, exist_ok=True)

    def download(asset):
        result = fetch(asset, args.cache, lambda *unused: None, cancellation)
        print("Verified", asset["name"], flush=True)
        return asset["name"], result

    downloaded = dict(ThreadPoolExecutor(4).map(download, assets))
    output.mkdir(parents=True, exist_ok=True)
    if args.platform == "windows":
        extract_zip(downloaded[runtime["name"]], output / "runtime")
        (output / "runtime/python313._pth").write_text("python313.zip\n.\n..\nLib/site-packages\nimport site\n")
        packages = output / "runtime/Lib/site-packages"
    else:
        with tarfile.open(downloaded[runtime["name"]]) as archive:
            archive.extractall(output / "extracted", filter="data")
        (output / "extracted/python").rename(output / "runtime")
        (output / "extracted").rmdir()
        packages = output / "runtime/lib/python3.13/site-packages"
    packages.mkdir(parents=True, exist_ok=True)
    for wheel in lock["wheels"][args.platform]:
        extract_zip(downloaded[wheel["name"]], packages)
    if args.platform == "linux":
        extra = output / "extra-extracted"
        subprocess.run(["dpkg-deb", "--extract", str(downloaded[lock["linux_extra"]["name"]]), str(extra)], check=True)
        library = next(extra.rglob("libxcb-cursor.so.0"))
        shutil.copyfile(library, output / "runtime/lib/libxcb-cursor.so.0")
        shutil.copyfile(extra / "usr/share/doc/libxcb-cursor0/copyright", output / "LICENSE-xcb-cursor.txt")
        shutil.rmtree(extra)
    shutil.copytree(ROOT / "mgebot_launcher", output / "mgebot_launcher",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "payload"))
    for name in ("run.py", "LICENSE", "THIRD_PARTY.md", "build-lock.json", "requirements.txt", "README.md", "README.ru.md", "CHANGELOG.md", "CHANGELOG.ru.md"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, output / name)
    for public_file in (output / "mgebot_launcher").rglob("*.py"):
        public_file.write_bytes(public_bytes(public_file))
    (output / "run.py").write_bytes(public_bytes(output / "run.py"))
    if args.payload:
        with zipfile.ZipFile(args.payload) as z:
            manifest = json.loads(z.read("MANIFEST.json"))
        if manifest["name"] != "mgebot duel" or manifest["version"] != json.loads((ROOT / "mgebot_launcher/dependencies.json").read_text())["plugin_version"] or manifest["platform"].casefold() != args.platform:
            raise ValueError("Wrong plugin payload")
        target = output / "mgebot_launcher/payload"
        target.mkdir()
        shutil.copy2(args.payload, target / "plugin.zip")
    if args.platform == "windows":
        compiler = shutil.which("x86_64-w64-mingw32-gcc") or shutil.which("gcc")
        if not compiler:
            raise SystemExit("A Windows-targeting MinGW-w64 compiler is required")

        environment = os.environ.copy(); environment["QT_QPA_PLATFORM"] = "offscreen"
        icon_script = "from PyQt6.QtWidgets import QApplication; from PyQt6.QtGui import QImage,QPainter; from PyQt6.QtSvg import QSvgRenderer; import sys; app=QApplication([]); image=QImage(256,256,QImage.Format.Format_ARGB32); image.fill(0); painter=QPainter(image); QSvgRenderer(sys.argv[1]).render(painter); painter.end(); assert image.save(sys.argv[2])"
        subprocess.run([sys.executable, "-c", icon_script, str(ROOT / "mgebot_launcher/assets/logo.svg"), str(output / "mgebot.ico")], env=environment, check=True)
        resource = output / "launcher.rc"
        resource.write_text('1 ICON "mgebot.ico"\n1 VERSIONINFO\nFILEVERSION 0,2,2,0\nPRODUCTVERSION 0,2,2,0\nBEGIN\n BLOCK "StringFileInfo"\n BEGIN\n  BLOCK "040904B0"\n  BEGIN\n   VALUE "CompanyName", "avxgroup"\n   VALUE "FileDescription", "mgebot duel local companion"\n   VALUE "FileVersion", "0.2.2"\n   VALUE "ProductName", "mgebot duel"\n   VALUE "ProductVersion", "0.2.2"\n  END\n END\n BLOCK "VarFileInfo"\n BEGIN\n  VALUE "Translation", 0x409, 1200\n END\nEND\n')
        windres = shutil.which("x86_64-w64-mingw32-windres") or shutil.which("windres")
        if not windres:
            raise SystemExit("MinGW-w64 windres is required for the Windows icon/version resource")
        subprocess.run([windres, str(resource), "-O", "coff", "-o", str(output / "resource.o")], cwd=output, check=True)
        command = [compiler, "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror", "-municode", "-mwindows", "-static-libgcc", "-Wl,--no-insert-timestamp",
                   str(ROOT / "scripts/launcher.c"), str(output / "resource.o"), "-o", str(output / "mgebot-duel.exe")]
        subprocess.run(command, check=True)
        resource.unlink(); (output / "resource.o").unlink()
    else:
        launcher = output / "mgebot-duel"
        launcher.write_text('#!/bin/sh\nset -eu\nAPP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nunset PYTHONHOME PYTHONPATH QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH\nexport PYTHONNOUSERSITE=1\nexport MGEBOT_ORIGINAL_LD_LIBRARY_PATH="${LD_LIBRARY_PATH-}"\nexport LD_LIBRARY_PATH="$APP_ROOT/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\nexec "$APP_ROOT/runtime/bin/python3" -B -s "$APP_ROOT/run.py" "$@"\n')
        launcher.chmod(0o755)
    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            if not path.resolve().is_relative_to(output):
                raise ValueError("Runtime symlink escapes the portable bundle")
            files[path.relative_to(output).as_posix()] = {"link": os.readlink(path)}
        elif path.is_file():
            files[path.relative_to(output).as_posix()] = {"sha256": digest(path), "bytes": path.stat().st_size}
    record = {"name": "mgebot duel companion", "version": __version__, "platform": args.platform,
              "developer_preview": args.runtime_only, "python": lock["python"], "plugin_payload_included": bool(args.payload),
              "plugin_sources_included": False, "credentials_included": False, "authenticode_signed": False,
              "packed_or_obfuscated": False, "files": files,
              "source_files": {p.relative_to(ROOT).as_posix(): hashlib.sha256(public_bytes(p)).hexdigest() for p in source_files()}}
    (output / "MANIFEST.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"build": str(output), "platform": args.platform, "files": len(files), "preview": args.runtime_only}), flush=True)


if __name__ == "__main__":
    main()
