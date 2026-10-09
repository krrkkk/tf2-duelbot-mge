#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tarfile
import zipfile
from pathlib import Path
from public_source import public_bytes

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (".gitignore", "LICENSE", "README.md", "README.ru.md", "CHANGELOG.md", "CHANGELOG.ru.md", "THIRD_PARTY.md",
                "requirements.txt", "build-lock.json", "run.py")
SOURCE_DIRECTORIES = ("mgebot_launcher", "scripts", "tests", ".github/workflows")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_files() -> list[Path]:
    files = [ROOT / name for name in SOURCE_FILES if (ROOT / name).is_file()]
    for name in SOURCE_DIRECTORIES:
        for path in (ROOT / name).rglob("*"):
            parts = path.relative_to(ROOT).parts
            if not path.is_file() or {"__pycache__", "payload"}.intersection(parts) or path.suffix in (".pyc", ".pyo"):
                continue
            if path.is_symlink() or path.suffix.casefold() in (".sp", ".inc", ".sq3", ".sqlite", ".smx", ".bsp"):
                raise ValueError(f"Private or unexpected source export entry: {path}")
            files.append(path)
    return sorted(files)


def verify_build(directory: Path) -> dict:
    manifest = json.loads((directory / "MANIFEST.json").read_text())
    if manifest.get("developer_preview") or not manifest.get("plugin_payload_included"):
        raise ValueError("Developer previews are not release artifacts")
    expected = manifest["files"]
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
              if p.is_file() or p.is_symlink()} - {"MANIFEST.json"}
    if actual != set(expected):
        raise ValueError(f"Build file set changed: {actual ^ set(expected)}")
    for name, spec in expected.items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Build path escapes its root")
        if "link" in spec:
            if not path.is_symlink() or os.readlink(path) != spec["link"]:
                raise ValueError(f"Changed link: {name}")
        elif path.is_symlink() or path.stat().st_size != spec["bytes"] or digest(path) != spec["sha256"]:
            raise ValueError(f"Changed build file: {name}")
    return manifest


def write_zip(path: Path, files: list[tuple[Path, str]], source_export=False):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source, name in files:
            if source.is_symlink():
                raise ValueError("Use tar.gz for builds containing symbolic links")
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | (0o755 if source.stat().st_mode & 0o111 else 0o644)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, public_bytes(source) if source_export else source.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build", type=Path, action="append", default=[])
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    import sys
    sys.path.insert(0, str(ROOT))
    from mgebot_launcher import __version__
    prefix = f"mgebot_duel_companion_{__version__}"
    sources = source_files()
    source_record = {p.relative_to(ROOT).as_posix(): hashlib.sha256(public_bytes(p)).hexdigest() for p in sources}
    source_path = output / f"{prefix}_Source.zip"
    write_zip(source_path, [(p, f"mgebot-duel-companion/{p.relative_to(ROOT).as_posix()}") for p in sources], source_export=True)
    artifacts = [source_path]
    builds = []
    for directory in args.build:
        directory = directory.resolve()
        manifest = verify_build(directory)
        if manifest["version"] != __version__:
            raise ValueError("Build and source versions differ")

        if manifest.get("source_files") != source_record:
            raise ValueError("Build does not match the exported source tree")
        if manifest["platform"] == "windows":
            artifact = output / f"{prefix}_Windows_x64.zip"
            write_zip(artifact, [(p, f"mgebot-duel/{p.relative_to(directory).as_posix()}")
                                 for p in sorted(directory.rglob("*")) if p.is_file()])
        elif manifest["platform"] == "linux":
            artifact = output / f"{prefix}_Linux_x64.tar.gz"
            with tarfile.open(artifact, "w:gz", compresslevel=6) as archive:
                archive.add(directory, arcname="mgebot-duel", recursive=True)
        else:
            raise ValueError("Unexpected build platform")
        artifacts.append(artifact)
        builds.append({"platform": manifest["platform"], "manifest_sha256": digest(directory / "MANIFEST.json"), "file": artifact.name})
    checksums = "".join(f"{digest(p)}  {p.name}\n" for p in artifacts)
    (output / "SHA256SUMS.txt").write_text(checksums)
    receipt = {"name": "mgebot duel companion", "version": __version__, "source_files": source_record,
               "builds": builds, "artifacts": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in artifacts}}
    (output / "RELEASE.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"out": str(output), "artifacts": receipt["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
