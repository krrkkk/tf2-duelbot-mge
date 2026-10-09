from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import sqlite3
import stat
import struct
import tempfile
import threading
import unittest
import zipfile
from dataclasses import asdict
from pathlib import Path

from mgebot_launcher.downloads import Cancelled, digest
from mgebot_launcher.history import read_sessions, totals
from mgebot_launcher.installer import Installer, archive_name, merge_spawn_config, unpack
from mgebot_launcher.presets import BotSettings, PresetStore
from mgebot_launcher.rcon import LocalConnection, _receive, _send
from mgebot_launcher.steam import find_tf_directories, parse_vdf


class LocalCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_discovery_multiple_steam_libraries(self):
        steam = self.root / "Steam"
        extra = self.root / "Another library"
        (steam / "steamapps").mkdir(parents=True)
        (steam / "steamapps/libraryfolders.vdf").write_text(f'"libraryfolders" {{ "0" {{ "path" "{steam}" }} "1" {{ "path" "{extra}" }} }}')
        tf = extra / "steamapps/common/Team Fortress 2/tf"
        tf.mkdir(parents=True)
        (tf / "gameinfo.txt").write_text('"GameInfo" { "game" "Team Fortress 2" "SteamAppId" "440" }')
        (extra / "steamapps/appmanifest_440.acf").write_text('"AppState" { "appid" "440" "installdir" "Team Fortress 2" }')
        self.assertEqual(find_tf_directories([steam]), [tf])
        self.assertEqual(parse_vdf('// test\n"a" { "path" "C:\\\\Steam" }')["a"]["path"], "C:\\Steam")

    def test_preset_roundtrip_no_credentials(self):
        store = PresetStore(self.root / "presets")
        settings = BotSettings.parse({"bot_class": 3, "skill_step": 9, "speed": 1.15, "accuracy": 62, "switchgun": True})
        original = store.save("Давление / Soldier", settings)
        path = self.root / "shared.json"
        store.export_file(original, path)
        imported = store.import_file(path)
        self.assertNotEqual(original.id, imported.id)
        self.assertEqual(original.settings, imported.settings)
        self.assertEqual(len(store.list()), 2)
        self.assertIn('"speed" "1.15"', settings.to_keyvalues())
        data = json.loads(path.read_text())
        data["password"] = "must-not-import"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            store.import_file(path)

    def test_preset_rejects_invalid_tactics_and_numbers(self):
        for invalid in [{"speed": float("nan")}, {"speed": "1.0"}, {"bot_class": True},
                        {"bot_class": 1, "switchgun": True}, {"bot_class": 3, "gunboats": True, "switchgun": True},
                        {"combo": True, "skill_step": 3}, {"accuracy": 101}, {"player_hp": -1},
                        {"bot_class": 5, "weapon_mode": 2}, {"regeneration": 999}]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                BotSettings.parse(invalid)

    def test_zip_rejects_traversal_links_and_duplicate_case(self):
        for label, entries in [("traversal", [("../escape", b"a", 0)]),
                               ("link", [("link", b"../escape", (stat.S_IFLNK | 0o777) << 16)]),
                               ("alias", [("Name.txt", b"a", 0), ("name.txt", b"b", 0)])]:
            archive = self.root / (label + ".zip")
            with zipfile.ZipFile(archive, "w") as z:
                for name, data, mode in entries:
                    entry = zipfile.ZipInfo(name)
                    entry.external_attr = mode
                    z.writestr(entry, data)
            with self.subTest(label=label), self.assertRaises(ValueError):
                unpack(archive, self.root / label, threading.Event())
        self.assertFalse((self.root / "escape").exists())
        for reserved in ("tf/NUL.cfg", "tf/con", "tf/folder./file", "tf/COM1.txt"):
            with self.subTest(reserved=reserved), self.assertRaises(ValueError):
                archive_name(reserved)

    def test_merge_preserves_existing_maps_and_comments(self):
        original = '// prefix\n"SpawnConfigs" {\n "old_map" { "note" "brace } inside" }\n} // suffix }\n'
        addition = '"SpawnConfigs" { "mge_triumph_beta7_rc1" { "Arena" { "spawn1" "1 2 3" } } }'
        merged = merge_spawn_config(original, addition, "mge_triumph_beta7_rc1")
        self.assertIn('// prefix', merged)
        self.assertTrue(merged.endswith('// suffix }\n'))
        self.assertEqual(parse_vdf(merged)["SpawnConfigs"]["old_map"], parse_vdf(original)["SpawnConfigs"]["old_map"])
        self.assertEqual(merge_spawn_config(merged, addition, "mge_triumph_beta7_rc1"), merged)

    def installer_fixture(self):
        tf = self.root / "game/tf"
        configs = tf / "addons/sourcemod/configs"
        configs.mkdir(parents=True)
        (tf / "gameinfo.txt").write_text('"GameInfo" { "game" "Team Fortress 2" }')
        (configs / "databases.cfg").write_text("private-existing-database-settings")
        (configs / "admins.cfg").write_text("private-existing-admins")
        (configs / "mgemod_spawns.cfg").write_text('"SpawnConfigs" { "old_map" { "1" { "name" "My arena" } } }')
        data = self.root / "app"
        cache = data / "cache"
        cache.mkdir(parents=True)
        archive = self.root / "dependency.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("addons/sourcemod/bin/runtime.so", b"dependency-runtime")
            z.writestr("addons/sourcemod/configs/databases.cfg", b"default-database-config")
            z.writestr("addons/sourcemod/configs/admins.cfg", b"default-admins")
            z.writestr("addons/sourcemod/scripting/not-needed.inc", b"source")
        asset = {"name": "sourcemod", "url": "https://github.com/alliedmodders/sourcemod/test.zip", "sha256": digest(archive), "size": archive.stat().st_size}
        (cache / (asset["sha256"] + ".download")).write_bytes(archive.read_bytes())
        files = {
            "tf/addons/sourcemod/plugins/mge_botduel.smx": b"synthetic-plugin-for-file-tests",
            "tf/maps/mge_triumph_beta7_rc1.bsp": b"synthetic-map-for-file-tests",
            "tf/addons/sourcemod/configs/mgemod_spawns.cfg": b'"SpawnConfigs" { "mge_triumph_beta7_rc1" { "1" { "name" "Spire" } } }',
        }
        manifest = {"name": "mgebot duel", "platform": "Linux", "version": "5.1.0", "source_code_included": False,
                    "sourcemod_included": False, "files": {name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)} for name, content in files.items()}}
        payload = self.root / "payload.zip"
        with zipfile.ZipFile(payload, "w") as z:
            for name, content in files.items():
                z.writestr(name, content)
            z.writestr("MANIFEST.json", json.dumps(manifest))
        catalog = {"plugin_version": "5.1.0", "map": "mge_triumph_beta7_rc1", "dependencies": {"linux": [asset]}}
        return tf, data, payload, Installer(data, catalog, process_check=lambda: False)

    def test_install_preserves_userdata_and_merges_map(self):
        tf, data, payload, installer = self.installer_fixture()
        result = installer.install(tf, payload, "linux", lambda *a: None, threading.Event())
        self.assertEqual(result["version"], "5.1.0")
        configs = tf / "addons/sourcemod/configs"
        self.assertEqual((configs / "databases.cfg").read_text(), "private-existing-database-settings")
        self.assertEqual((configs / "admins.cfg").read_text(), "private-existing-admins")
        self.assertFalse((tf / "addons/sourcemod/scripting").exists())
        maps = parse_vdf((configs / "mgemod_spawns.cfg").read_text())["SpawnConfigs"]
        self.assertEqual(set(maps), {"old_map", "mge_triumph_beta7_rc1"})
        credentials = json.loads((data / "connection.json").read_text())
        self.assertEqual(len(credentials["password"]), 64)
        self.assertIn(credentials["password"], (tf / "cfg/mgebot-launcher.cfg").read_text())
        again = installer.install(tf, payload, "linux", lambda *a: None, threading.Event())
        self.assertEqual(again["files_changed"], 0)

    def test_install_rolls_back_partial_mutation(self):
        tf, data, payload, installer = self.installer_fixture()
        before = {p.relative_to(tf): p.read_bytes() for p in tf.rglob("*") if p.is_file()}

        def fail(phase, current, total):
            if phase == "Install" and current == 2:
                raise RuntimeError("simulated write interruption")

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            installer.install(tf, payload, "linux", fail, threading.Event())
        after = {p.relative_to(tf): p.read_bytes() for p in tf.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertFalse((data / "connection.json").exists())
        self.assertEqual(json.loads(next((data / "transactions").glob("*/journal.json")).read_text())["status"], "rolled_back")

    def test_install_does_not_follow_game_symlink(self):
        if os.name == "nt":
            self.skipTest("Creating Windows symlinks needs separate OS rights")
        tf, data, payload, installer = self.installer_fixture()
        outside = self.root / "outside"
        outside.mkdir()
        (tf / "maps").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            installer.install(tf, payload, "linux", lambda *a: None, threading.Event())
        self.assertEqual(list(outside.iterdir()), [])

    def test_history_does_not_change_database(self):
        tf = self.root / "tf"
        path = tf / "addons/sourcemod/data/sqlite/botduel.sq3"
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE botduel_sessions (id TEXT,steamid TEXT,name TEXT,started INTEGER,ended INTEGER,status TEXT,reason TEXT,map TEXT,arena TEXT,profile TEXT,modified INTEGER,player_score INTEGER,bot_score INTEGER,active_seconds REAL,damage_out INTEGER,damage_in INTEGER,hits INTEGER,airshots INTEGER)")
            db.execute("INSERT INTO botduel_sessions VALUES ('test','fixture','Example',1,2,'completed','win','testmap','Spire','test',0,20,9,120,800,300,10,2)")
        db.close()
        before = path.read_bytes()
        rows = read_sessions(tf)
        self.assertEqual(totals(rows)["dpm"], 400)
        self.assertEqual(path.read_bytes(), before)

    def test_local_rcon_fragmented_response(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        failures = []

        def serve():
            try:
                with server, server.accept()[0] as stream:
                    request, kind, secret = _receive(stream)
                    self.assertEqual((kind, secret), (3, b"local-secret"))
                    _send(stream, request, 0, b"")
                    _send(stream, request, 2, b"")
                    request, kind, command = _receive(stream)
                    self.assertEqual(command, b"sm_duel_local status")
                    end, _, _ = _receive(stream)
                    _send(stream, request, 0, b'MGBOT_LOCAL {"api":1,')
                    _send(stream, request, 0, b'"ok":true,"version":"5.1.0"}\n')
                    _send(stream, end, 0, b"")
            except BaseException as exc:
                failures.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.assertEqual(LocalConnection(port, "local-secret").api("status")["version"], "5.1.0")
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures, failures)
        with self.assertRaises(ValueError):
            LocalConnection(port, "local-secret").api("apply", "1;quit")


if __name__ == "__main__":
    unittest.main()
