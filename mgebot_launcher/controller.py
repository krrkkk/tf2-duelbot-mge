from __future__ import annotations

import json
import logging
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from .downloads import Cancelled, digest
from .crashlog import start_watch
from .history import read_sessions
from .installer import Installer
from .local import FileConnection, LocalNotReady, load_file_connection
from .presets import BotSettings, SessionSettings
from .steam import (find_tf_directories, launch_training, parse_vdf,
                    running_games, validate_tf_directory)
from .storage import atomic_bytes, read_json, write_json


class JobSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal()


class Job(QRunnable):
    def __init__(self, work):
        super().__init__(); self.work = work; self.signals = JobSignals()

    def run(self):
        try: self.signals.result.emit(self.work(self.signals.progress.emit))
        except Exception as error: self.signals.error.emit(error)
        finally: self.signals.finished.emit()


class Controller(QObject):
    def __init__(self, window, data: Path, demo=False):
        super().__init__(window)
        self.window = window; self.data = data; self.demo = demo
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(3); self.jobs = set()
        self.polling = self.discovering = self.action_busy = self.history_busy = False
        self.userid = 0; self.connection = None; self.tf_directory = None; self.game = None
        self.pending_launch = None; self.generation = 0; self.last_discovery = 0.0
        self.last_history = 0.0; self.last_map = ""; self.disk_ready = False; self.runtime_mismatch = False
        self.last_error = ""; self.last_bootstrap = 0.0; self.pending_bootstrap = False
        self.watched_game = None
        self.cancel = threading.Event()
        self.catalog = json.loads((Path(__file__).parent / "dependencies.json").read_text())
        self.payload = Path(window.payload) if window.payload else Path(__file__).parent / "payload/plugin.zip"
        self.payload_manifest = None
        if self.payload.is_file():
            with zipfile.ZipFile(self.payload) as archive:
                self.payload_manifest = json.loads(archive.read("MANIFEST.json"))
        window.primary_requested.connect(self.primary)
        window.install_requested.connect(self.install)
        window.cancel_requested.connect(self.cancel.set)
        window.detect_requested.connect(self.discover)
        window.directory_changed.connect(self.change_directory)
        window.apply_requested.connect(self.apply)
        window.launch_requested.connect(self.launch)
        window.stop_requested.connect(self.stop)
        window.history_requested.connect(self.history)
        self.timer = QTimer(self); self.timer.setInterval(1600); self.timer.timeout.connect(self.tick)
        if not demo:
            self.timer.start(); QTimer.singleShot(0, self.discover)

    def submit(self, work, success=None, failure=None, finished=None, progress=None):
        job = Job(work); self.jobs.add(job)
        if success: job.signals.result.connect(success)
        job.signals.error.connect(failure or self.error)
        if finished: job.signals.finished.connect(finished)
        if progress: job.signals.progress.connect(progress)
        job.signals.finished.connect(lambda: self.jobs.discard(job))
        self.pool.start(job)

    def error(self, error):
        if isinstance(error, Cancelled): self.window.notify(self.window.t("cancel")); return
        logging.warning("Companion operation: %s", error)
        self.window.notify(self.window.t("error") + ": " + str(error), True)

    def tick(self):
        if self.demo or self.window.busy: return
        if time.monotonic() - self.last_discovery > 10: self.discover()
        self.poll()
        if self.window.online and time.monotonic() - self.last_history > 12: self.history()

    def change_directory(self, directory):
        self.generation += 1; self.userid = 0; self.connection = None; self.pending_launch = None
        self.window.set_launch_pending(False)
        self.tf_directory = None; self.last_map = ""; self.disk_ready = False; self.runtime_mismatch = False
        self.window.game_directory = directory; self.window.install_ready = False
        self.window.show_snapshot({}); self.window.set_connection_state("checking"); self.discover()

    def _installed(self, tf):
        if not self.payload_manifest or not load_file_connection(tf): return False
        critical = ["tf/addons/sourcemod/plugins/mge_botduel.smx", "tf/addons/sourcemod/plugins/mgebot_companion.smx"]
        for name in critical:
            spec = self.payload_manifest.get("files", {}).get(name); path = tf.parent / name
            if not spec or not path.is_file() or digest(path) != spec["sha256"]: return False
        return (tf / ("maps/" + self.catalog["map"] + ".bsp")).is_file() and (tf / "addons/sourcemod/configs/databases.cfg").is_file()

    def discover(self):
        if self.demo or self.discovering or self.window.busy: return
        self.discovering = True; self.last_discovery = time.monotonic(); generation = self.generation
        chosen = self.window.game_directory
        def work(progress):
            folders = find_tf_directories(); tf = None
            if chosen:
                try: tf = validate_tf_directory(Path(chosen))
                except (ValueError, OSError): pass
            if tf is None and folders: tf = folders[0]
            games = running_games()
            game = next((g for g in games if tf and g.tf_directory == tf), None)
            if game is None and len(games) == 1 and games[0].tf_directory is None: game = games[0]
            return tf, game, bool(tf and self._installed(tf))
        def found(result):
            if generation != self.generation: return
            tf, game, ready = result; self.game = game; self.disk_ready = ready
            if tf and game and game.tf_directory == tf and game.pid != self.watched_game:
                try: start_watch(self.data, tf, game); self.watched_game = game.pid
                except OSError as error: logging.warning("TF2 crash recorder: %s", error)
            elif game is None: self.watched_game = None
            self.window.install_ready = ready and not self.runtime_mismatch
            if tf:
                changed = tf != self.tf_directory; self.tf_directory = tf; self.window.game_directory = str(tf)
                connection = load_file_connection(tf)
                if connection and (not self.connection or self.connection.installation != connection.installation or self.connection.tf_directory != tf):
                    self.connection = connection
                if changed:
                    self._offline_arenas(); self.history(); self.window._save_preferences()
            if not self.window.online and not self.pending_launch:
                if not tf: self.window.set_connection_state("missing_game")
                elif not ready: self.window.set_connection_state("not_installed")
                elif game and game.insecure is False: self.window.set_connection_state("secure_game")
                elif game: self.window.set_connection_state("running_unknown")
                else: self.window.set_connection_state("idle")
            self.poll()
        self.submit(work, found, finished=lambda: setattr(self, "discovering", False))

    def _offline_arenas(self):
        if not self.tf_directory: return
        file = self.tf_directory / "addons/sourcemod/configs/mgemod_spawns.cfg"
        try:
            document = parse_vdf(file.read_text(encoding="utf-8-sig")); maps = next(iter(document.values()))
            arenas = maps.get(self.catalog["map"], {})
            self.window.set_arenas([{"id": i + 1, "name": str(value.get("name", name)), "occupied": False}
                                   for i, (name, value) in enumerate(arenas.items()) if isinstance(value, dict)])
        except (OSError, ValueError, AttributeError, StopIteration): pass

    def primary(self):
        if self.demo or self.window.busy or self.action_busy: return
        if not self.window.install_ready:
            if not self.window.game_directory and not self.window._pick_directory(): return
            self.install(self.window.game_directory, self.window.payload); return
        if self.window.online and self.window.last_snapshot.get("active"):
            return
        self.launch(self.window.settings(), int(self.window.arena_box.currentData() or 0))

    def install(self, folder: str, archive: str = ""):
        if self.demo or self.window.busy: return
        try:
            tf = validate_tf_directory(Path(folder))
            payload = Path(archive) if archive else self.payload
            if not payload.is_file(): raise FileNotFoundError("Use the complete application release; its map and plugin are included")
        except (ValueError, OSError) as error: self.error(error); return
        self.cancel.clear(); self.window.set_busy(True)
        game = self.game
        live = bool(game and game.insecure is True and game.tf_directory == tf)
        installer = Installer(self.data, self.catalog)
        def installed(result):
            self.tf_directory = tf; self.window.game_directory = str(tf); self.runtime_mismatch = False
            self.connection = load_file_connection(tf); self.window.install_ready = True; self.disk_ready = True
            self.window._save_preferences(); self.window.set_connection_state("idle"); self._offline_arenas()
            self.window.notify(self.window.t("installed"))
            if live and game:
                self.last_bootstrap = time.monotonic()
                self.submit(lambda progress: launch_training(27025, self.catalog["map"], tf, game, bootstrap_only=True, refresh=True))
            QTimer.singleShot(400, self.poll)
        platform = "windows" if sys.platform == "win32" else "linux"
        self.submit(lambda progress: installer.install(tf, payload, platform, progress, self.cancel, allow_running_local=live),
                    installed, finished=lambda: self.window.set_busy(False), progress=self.window.install_progress)

    def poll(self):
        if self.demo or self.polling or self.window.busy or self.action_busy or not self.connection: return
        self.polling = True; connection = self.connection; generation = self.generation
        previous_map = self.last_map
        def work(progress):
            connection.heartbeat()
            status = connection.api("status")
            if status.get("version") != self.catalog["plugin_version"]:
                raise LocalNotReady("update_required", "The running bot plugin needs an update/reload")
            players = connection.api("players")["players"]
            selected = next((p for p in players if p.get("host")), players[0] if len(players) == 1 else None)
            arenas = connection.api("arenas")["arenas"] if status.get("map") != previous_map else None
            snapshot = connection.api("snapshot", selected["userid"]) if selected else {}
            try:
                write_json(self.data / "watch/latest-session.json", {"at": time.time(), "map":status.get("map"),
                           "plugin_version":status.get("version"), "settings":snapshot.get("settings"),
                           "session_settings":snapshot.get("session_settings"), "session":snapshot.get("session"),
                           "decision":snapshot.get("decision")})
            except OSError:
                pass
            return status, selected, arenas, snapshot
        def received(result):
            if generation != self.generation: return
            status, player, arenas, snapshot = result; self.last_map = status.get("map", "")
            self.last_error = ""; self.runtime_mismatch = False; self.userid = player["userid"] if player else 0
            self.window.install_ready = self.disk_ready
            self.window.set_connection_state("connected" if player else "joining")
            if arenas is not None: self.window.set_arenas(arenas)
            self.window.show_snapshot(snapshot)
            if snapshot.get("settings") and not self.window.dirty and not self.pending_launch:
                try:
                    self.window.set_settings(BotSettings.parse(snapshot["settings"]))
                    if snapshot.get("session_settings"): self.window.set_session_settings(SessionSettings.parse(snapshot["session_settings"]))
                except ValueError as error: self.error(error)
            if self.pending_launch and player:
                pending = self.pending_launch; self.pending_launch = None
                self.window.set_launch_pending(False)
                arena = pending["arena"] or next((a["id"] for a in self.window.arenas if not a.get("occupied")), 0)
                self._apply(pending["settings"], arena, pending["environment"])
            elif self.pending_launch:
                self._pending_tick(allow_bootstrap=False)
        def disconnected(error):
            if generation != self.generation: return
            self.userid = 0
            stage = error.stage if isinstance(error, LocalNotReady) else "error"
            if stage == "update_required": self.runtime_mismatch = True; self.window.install_ready = False
            if not self.game and not self.pending_launch and stage in ("waiting_map", "waiting_plugin"): stage = "idle"
            self.window.set_connection_state(stage, str(error)); self.window.show_snapshot({})
            if str(error) != self.last_error:
                logging.info("Local connection stage=%s: %s", stage, error); self.last_error = str(error)
            self._pending_tick()
        self.submit(work, received, disconnected, finished=lambda: setattr(self, "polling", False))

    def _pending_tick(self, allow_bootstrap=True):
        if not self.pending_launch: return
        pending = self.pending_launch; now = time.monotonic()
        if now > pending["deadline"]:
            self.pending_launch = None; self.window.set_launch_pending(False); self.window.notify(self.window.t("connect_first") + " " + self.last_error, True); return


        if allow_bootstrap and pending.get("bootstrap") and now - pending["started"] > 3.5 and self.game:
            pending["bootstrap"] = False
            self.submit(lambda progress: launch_training(27025, self.catalog["map"], self.tf_directory, self.game))

    def _apply(self, settings: BotSettings, arena: int | None = None, environment: SessionSettings | None = None):
        if not self.connection or not self.userid:
            self.window.notify(self.window.t("connect_first"), True); return
        if self.action_busy or self.demo: return
        self.action_busy = True; self.window.set_action_busy(True)
        environment = environment or self.window.session_settings(); userid = self.userid
        connection = self.connection; tf = self.tf_directory; generation = self.generation
        def work(progress):
            if tf is None or connection.tf_directory != tf: raise ValueError("The selected TF2 installation changed")
            identifier = uuid.uuid4().hex; directory = tf / "addons/sourcemod/configs/botduel_local"
            if directory.is_symlink() or not directory.resolve().is_relative_to(tf): raise ValueError("Preset directory is outside TF2")
            file = directory / (identifier + ".cfg"); session = directory / (identifier + "-session.cfg")
            atomic_bytes(file, settings.to_keyvalues().encode()); atomic_bytes(session, environment.to_keyvalues().encode())
            try:
                if arena is not None:
                    if arena <= 0: raise ValueError(self.window.t("arena_pending"))
                    return connection.api("start", userid, arena, identifier)
                return connection.api("apply", userid, identifier)
            finally:
                file.unlink(missing_ok=True); session.unlink(missing_ok=True)
        def done(result):
            if generation != self.generation: return
            self.window.mark_dirty(self.window.settings() != settings or self.window.session_settings() != environment)
            self.window.notify(self.window.t("restarted") if result.get("restarted") else self.window.t("applied"))
        def finished():
            self.action_busy = False; self.window.set_action_busy(False); QTimer.singleShot(100, self.poll)
        self.submit(work, done, finished=finished)

    def apply(self, settings): self._apply(settings)

    def launch(self, settings, arena):
        if self.demo or self.action_busy or self.pending_launch: return
        if self.connection and self.userid and self.window.online:
            self._apply(settings, arena); return
        if not self.connection or not self.tf_directory:
            self.window._select_page(0); self.window.notify(self.window.t("select_game"), True); return
        game = self.game
        if game and game.insecure is not True:
            self.window.set_connection_state("secure_game"); self.window.notify(self.window.t("local_launch_note"), True); return
        self.pending_launch = {"settings": settings, "environment": self.window.session_settings(), "arena": arena,
                               "deadline": time.monotonic() + 120, "started": time.monotonic(), "bootstrap": bool(game)}
        self.window.set_launch_pending(True)
        self.window.set_connection_state("starting")
        try: start_watch(self.data, self.tf_directory, game)
        except OSError as error: logging.warning("TF2 crash recorder: %s", error)
        def failed(error):
            self.pending_launch = None; self.window.set_launch_pending(False); self.window.set_connection_state("error", str(error)); self.error(error)
        self.submit(lambda progress: launch_training(27025, self.catalog["map"], self.tf_directory, game, bootstrap_only=bool(game)),
                    lambda _: QTimer.singleShot(400, self.poll), failed)

    def stop(self):
        if self.demo or self.action_busy or not self.connection or not self.userid: return
        self.action_busy = True; self.window.set_action_busy(True); userid = self.userid; connection = self.connection
        def finished():
            self.action_busy = False; self.window.set_action_busy(False); QTimer.singleShot(100, self.poll); QTimer.singleShot(300, self.history)
        self.submit(lambda progress: connection.api("stop", userid), finished=finished)

    def history(self):
        if self.demo or self.history_busy or not self.tf_directory: return
        self.history_busy = True; self.last_history = time.monotonic(); directory = self.tf_directory; generation = self.generation
        def received(rows):
            if generation == self.generation: self.window.show_history(rows)
        self.submit(lambda progress: read_sessions(directory), received, finished=lambda: setattr(self, "history_busy", False))
