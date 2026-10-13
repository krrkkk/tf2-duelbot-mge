from __future__ import annotations


import os
import sys
from dataclasses import asdict
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")

from PyQt6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve, QUrl
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QKeySequence, QShortcut, QDesktopServices
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox,
    QDialog, QFileDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QScrollArea, QSizeGrip, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import __version__
from .i18n import CLASSES_RU, text
from .presets import BotSettings, CLASS_NAMES, Preset, PresetStore, SessionSettings, PracticeSettings
from .storage import read_json, write_json
from .theme import STYLESHEET
from .widgets import ActionButton, ClassButton, NumericControl, Toggle, WindowBar, WelcomeReveal, icon, ASSETS


def duration(seconds):
    hours, rest = divmod(max(0, round(seconds)), 3600)
    minutes, second = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{second:02}" if hours else f"{minutes}:{second:02}"


class MainWindow(QMainWindow):
    primary_requested = pyqtSignal()
    install_requested = pyqtSignal(str, str)
    cancel_requested = pyqtSignal()
    detect_requested = pyqtSignal()
    directory_changed = pyqtSignal(str)
    launch_requested = pyqtSignal(object, int)
    apply_requested = pyqtSignal(object)
    teammate_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    history_requested = pyqtSignal()

    def __init__(self, data: Path, payload: Path | None = None, demo=False):
        super().__init__()
        self.data = data; self.store = PresetStore(data / "presets")
        self.preferences = read_json(data / "ui.json", {})
        self.language = self.preferences.get("language", "en")
        self.motion = bool(self.preferences.get("motion", True))
        self.mode = self.preferences.get("mode", "solo")
        if self.mode not in ("solo", "duo"): self.mode = "solo"
        self.visibility = self.preferences.get("visibility", "friends")
        if self.visibility not in ("friends", "unlisted", "listed"): self.visibility = "friends"
        self.host_class = self.preferences.get("host_class", 3)
        if self.host_class not in (1, 3, 4): self.host_class = 3
        self._base_settings = BotSettings()
        self.demo = demo; self.payload = str(payload) if payload else ""
        connection = read_json(data / "connection.json", {})
        self.game_directory = connection.get("tf_directory", self.preferences.get("tf_directory", ""))
        self.current_preset = self.preferences.get("preset")
        self.dirty = self.online = self.busy = self.action_busy = self._loading = self._closing = False
        self.install_ready = False; self.connection_stage = "checking"; self.connection_detail = ""
        self.launch_pending = False
        self.arenas = []; self.sessions = []; self.last_snapshot = {}; self.presets = []
        self.setWindowTitle("mgebot duel")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(QIcon(str(ASSETS / "logo.webp")))
        self.setMinimumSize(1000, 730); self.resize(1200, 820)
        for file in (ASSETS / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(file))
        self.setFont(QFont("Manrope", 10))
        arrow = (ASSETS / "icons/chevron.svg").as_posix().replace('"', '\\"')
        self.setStyleSheet(STYLESHEET + f'\nQComboBox::down-arrow {{ image:url("{arrow}"); }}')
        self._build(BotSettings(), SessionSettings())
        for key, page in (("Ctrl+1", 0), ("Ctrl+2", 1)):
            QShortcut(QKeySequence(key), self, activated=lambda n=page: self._select_page(n))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save_preset)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._apply)
        if self.motion:
            QTimer.singleShot(0, self._intro)

    def t(self, key):
        return text(key, self.language)

    def label(self, value, role=None, wrap=False):
        label = QLabel(value); label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(wrap)
        if role: label.setObjectName(role)
        return label

    def button(self, key, callback=None, primary=False, symbol=None):
        result = ActionButton(self.t(key), symbol, primary)
        if callback: result.clicked.connect(lambda checked=False: callback())
        return result

    def panel(self, name="Panel"):
        frame = QFrame(); frame.setObjectName(name)
        layout = QVBoxLayout(frame); layout.setContentsMargins(22, 20, 22, 20); layout.setSpacing(14)
        return frame, layout

    def _build(self, draft, environment, practice=None):
        self._loading = True
        shell = QWidget(); outside = QVBoxLayout(shell); outside.setContentsMargins(5, 5, 5, 5)
        root = QFrame(); root.setObjectName("Workspace"); overall = QVBoxLayout(root); overall.setContentsMargins(0, 0, 0, 0); overall.setSpacing(0)
        bar = WindowBar(); bar.setObjectName("WindowBar"); bar.setFixedHeight(68)
        line = QHBoxLayout(bar); line.setContentsMargins(20, 0, 12, 0); line.setSpacing(9)
        mark = self.label(""); mark.setPixmap(self.windowIcon().pixmap(44, 44)); mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        line.addWidget(mark)
        brand = self.label("mgebot duel", "Brand"); brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); line.addWidget(brand); line.addSpacing(22)
        self.nav = []
        for index, key in enumerate(("play_page", "bots_page")):
            button = self.button(key, lambda n=index: self._select_page(n)); button.setCheckable(True); button.setFixedHeight(34); button.setProperty("ghost", True)
            line.addWidget(button); self.nav.append(button)
        line.addStretch()
        self.language_box = QComboBox(); self.language_box.addItem("EN", "en"); self.language_box.addItem("RU", "ru"); self.language_box.setFixedWidth(92)
        self.language_box.setAccessibleName(self.t("language")); self.language_box.setCurrentIndex(0 if self.language == "en" else 1)
        self.language_box.currentIndexChanged.connect(self._change_language); line.addWidget(self.language_box)
        preferences = ActionButton("", "settings"); preferences.setFixedSize(36, 34); preferences.setToolTip(self.t("app_settings")); preferences.setAccessibleName(self.t("app_settings")); preferences.clicked.connect(self._preferences); line.addWidget(preferences)
        for symbol, callback, title in (("minimize", self.showMinimized, "minimize"), ("maximize", self._maximize, "maximize"), ("close", self.close, "close")):
            button = ActionButton("", symbol); button.setFixedSize(32, 32); button.setAccessibleName(self.t(title)); button.setToolTip(self.t(title)); button.clicked.connect(callback); line.addWidget(button)
        overall.addWidget(bar)
        content = QVBoxLayout(); content.setContentsMargins(24, 20, 24, 10); content.setSpacing(14)
        self.message = self.label("", "Message", True); self.message.hide(); content.addWidget(self.message)
        if self.demo: content.addWidget(self.label(self.t("demo"), "Message", True))
        self.pages = QStackedWidget(); self.pages.addWidget(self._play_page()); self.pages.addWidget(self._bots_page()); content.addWidget(self.pages, 1)
        footer = QHBoxLayout(); footer.addWidget(self.label(f"{__version__}  ·  avxgroup", "Muted")); footer.addStretch()
        self.connection_status = self.label("", "Muted"); footer.addWidget(self.connection_status)
        grip = QSizeGrip(shell); grip.setFixedSize(16, 16); footer.addWidget(grip); content.addLayout(footer)
        overall.addLayout(content, 1); outside.addWidget(root); self.setCentralWidget(shell)
        self.set_settings(draft); self.set_session_settings(environment); self.set_practice_settings(practice or PracticeSettings()); self.load_presets()
        self._loading = False; self.set_arenas(self.arenas); self.show_snapshot(self.last_snapshot)
        self._select_page(0); self.set_connection_state(self.connection_stage, self.connection_detail); self.set_busy(self.busy)

    def _maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _intro(self):
        if not self.motion or self.demo: return
        self.welcome = WelcomeReveal(self.pages)

    def _select_page(self, index):
        if index not in (0, 1): return
        self.pages.setCurrentIndex(index)
        for n, button in enumerate(self.nav): button.setChecked(n == index)


    def _play_page(self):
        page = QWidget(); page.setObjectName("PlayContent"); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(18)
        hero, area = self.panel("Hero")
        row = QHBoxLayout(); row.setSpacing(22); row.setContentsMargins(0, 0, 0, 0)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.hero_class_icon = self.label(""); self.hero_class_icon.setFixedSize(128, 128); self.hero_class_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); self.hero_class_icon.setPixmap(self.windowIcon().pixmap(128, 128)); row.addWidget(self.hero_class_icon)
        copy = QVBoxLayout(); copy.setSpacing(14)
        self.hero_title = self.label(self.t("hero_install"), "HeroTitle", True); copy.addWidget(self.hero_title)
        self.hero_description = self.label(self.t("hero_install_note"), "Muted", True); self.hero_description.setMaximumWidth(620); copy.addWidget(self.hero_description)
        self.stage_label = self.label(self.t("checking"), "Status"); self.stage_label.setMaximumWidth(340)
        row.addLayout(copy, 1)
        area.addLayout(row)
        modes = QHBoxLayout(); modes.setSpacing(12); self.mode_buttons = {}; self.mode_group = QButtonGroup(self); self.mode_group.setExclusive(True)
        for mode, key in (("solo", "mode_solo"), ("duo", "mode_duo")):
            button = self.button(key, lambda m=mode: self._set_mode(m)); button.setCheckable(True); self.mode_group.addButton(button); button.setChecked(mode == self.mode); button.setMinimumHeight(52)
            button.setAccessibleName(self.t(key)); modes.addWidget(button, 1); self.mode_buttons[mode] = button
        area.addLayout(modes)
        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.setFixedHeight(7); self.progress.hide(); area.addWidget(self.progress)
        actions = QHBoxLayout(); location = QVBoxLayout(); location.setSpacing(5)
        location.addWidget(self.stage_label, 0, Qt.AlignmentFlag.AlignLeft)
        self.folder_label = self.label(self.t("find_game"), "Muted"); location.addWidget(self.folder_label); actions.addLayout(location, 1)
        self.cancel_button = self.button("cancel", self.cancel_requested.emit); self.cancel_button.hide(); actions.addWidget(self.cancel_button)
        self.main_button = self.button("install_main", self.primary_requested.emit, True, "download"); self.main_button.setMinimumSize(210, 52); actions.addWidget(self.main_button)
        area.addLayout(actions); layout.addWidget(hero)
        lower = QHBoxLayout(); lower.setSpacing(18)
        setup, form = self.panel(); form.addWidget(self.label(self.t("your_setup"), "Section"))
        self.preset_box = QComboBox(); self.preset_box.setAccessibleName(self.t("preset")); self.preset_box.currentIndexChanged.connect(self._choose_preset); form.addWidget(self.preset_box)
        form.addWidget(self.label(self.t("arena"), "Muted"))
        self.arena_box = QComboBox(); self.arena_box.setAccessibleName(self.t("arena")); form.addWidget(self.arena_box)
        self.setup_summary = self.label("", None, True); form.addWidget(self.setup_summary)
        self.host_panel = QWidget(); host = QVBoxLayout(self.host_panel); host.setContentsMargins(0, 0, 0, 0); host.setSpacing(9)
        host_row = QHBoxLayout(); host_row.setSpacing(12); host_class_column = QVBoxLayout(); visibility_column = QVBoxLayout()
        host_class_column.addWidget(self.label(self.t("your_class"), "FieldLabel"))
        self.host_class_box = QComboBox(); self.host_class_box.setAccessibleName(self.t("your_class"))
        for cls in (1, 3, 4): self.host_class_box.addItem((CLASSES_RU if self.language == "ru" else CLASS_NAMES)[cls], cls)
        self.host_class_box.setCurrentIndex(self.host_class_box.findData(self.host_class)); self.host_class_box.currentIndexChanged.connect(self._host_changed); host_class_column.addWidget(self.host_class_box)
        self.visibility_box = QComboBox(); self.visibility_box.setAccessibleName(self.t("room_access"))
        for mode in ("friends", "unlisted", "listed"): self.visibility_box.addItem(self.t("visibility_" + mode), mode)
        self.visibility_box.setCurrentIndex(self.visibility_box.findData(self.visibility)); self.visibility_box.currentIndexChanged.connect(self._host_changed)
        visibility_column.addWidget(self.label(self.t("room_access"), "FieldLabel")); visibility_column.addWidget(self.visibility_box)
        host_row.addLayout(host_class_column, 1); host_row.addLayout(visibility_column, 2); host.addLayout(host_row)
        form.addWidget(self.host_panel)

        form.addStretch(); self.configure_button = self.button("configure_bot", lambda: self._select_page(1), symbol="settings"); form.addWidget(self.configure_button)
        lower.addWidget(setup, 1)
        live, content = self.panel(); content.setSpacing(9)
        heading = QHBoxLayout(); heading.addWidget(self.label(self.t("session"), "Section"), 1)
        self.player_label = self.label(self.t("player"), "Muted"); self.player_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.player_label.customContextMenuRequested.connect(self._player_menu); heading.addWidget(self.player_label); content.addLayout(heading)
        self.session_empty = self.label(self.t("no_session"), "Muted", True); self.session_empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.session_empty.setMinimumHeight(100); content.addWidget(self.session_empty, 1)
        self.health_widget = QWidget(); health = QHBoxLayout(self.health_widget); health.setContentsMargins(0, 0, 0, 0); health.setSpacing(15)
        self.score = self.label("— : —", "Score"); health.addWidget(self.score)
        self.health_bars = {}; self.live_labels = {}
        for who in ("player", "bot"):
            column = QVBoxLayout(); label = self.label(self.t(who) + " · — HP", "Muted"); self.live_labels[who + "_hp"] = label; column.addWidget(label)
            bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(0); bar.setTextVisible(False); bar.setFixedHeight(6); self.health_bars[who] = bar; column.addWidget(bar); health.addLayout(column)
        content.addWidget(self.health_widget)
        self.team_label = self.label("", "TeamState", True); content.addWidget(self.team_label)
        self.decision_label = self.label(self.t("plan_waiting"), "Accent", True); content.addWidget(self.decision_label)
        self.teammate_button = self.button("add_bot_teammate", self.teammate_requested.emit, symbol="play"); content.addWidget(self.teammate_button)
        self.invite_button = self.button("invite_friend", self._invite_friend, symbol="copy"); content.addWidget(self.invite_button)
        self.invite_hint = self.label(self.t("invite_note"), "Muted", True); content.addWidget(self.invite_hint)
        content.addStretch()
        actions = QHBoxLayout(); self.stop_button = self.button("stop", self.stop_requested.emit, symbol="stop"); actions.addWidget(self.stop_button)
        self.new_duel_button = self.button("new_duel", self._launch, symbol="play"); actions.addWidget(self.new_duel_button); content.addLayout(actions)
        lower.addWidget(live, 1); layout.addLayout(lower, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); return scroll

    def _bots_page(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(16)
        top = QHBoxLayout(); top.addWidget(self.label(self.t("bots_title"), "Title")); top.addStretch()
        top.addWidget(self.button("save", self._save_preset))
        more = self.button("preset_actions", symbol="more"); menu = QMenu(more)
        menu.addAction(self.t("save_as"), lambda: self._save_preset(True)); menu.addAction(self.t("rename"), self._rename_preset); menu.addAction(self.t("delete"), self._delete_preset)
        menu.addSeparator(); menu.addAction(self.t("import"), self._import_preset); menu.addAction(self.t("export"), self._export_preset); more.setMenu(menu); top.addWidget(more)
        outer.addLayout(top)
        self.class_group = QButtonGroup(self); self.class_group.setExclusive(True); self.class_buttons = {}
        classes = QHBoxLayout(); classes.setSpacing(7)
        names = CLASSES_RU if self.language == "ru" else CLASS_NAMES
        for class_id, name in names.items():
            filename = CLASS_NAMES[class_id].lower(); button = ClassButton(class_id, name, filename); self.class_group.addButton(button, class_id); self.class_buttons[class_id] = button; classes.addWidget(button, 1)
        self.class_group.idClicked.connect(self._edited); self.class_selector = QWidget(); self.class_selector.setLayout(classes); outer.addWidget(self.class_selector)
        frame, inner = self.panel(); inner.setContentsMargins(18, 4, 18, 12)
        self.duo_note = self.label(self.t("duo_settings_note"), "Message", True); outer.addWidget(self.duo_note)
        self.settings_tabs = QTabWidget(); self.controls = {}; self.session_controls = {}; self.practice_controls = {}

        groups = [
            ("combat", ["skill_step", "accuracy", "weapon_mode", "gunboats", "switchgun", "headshots_only", "quickswitch", "shotgun_deny", "shotgun_stall", "wait_soldier", "respawn_sound"]),
            ("rules", ["player_hp", "bot_hp", "ammo_policy", "frag_limit", "player_ammo", "bot_ammo", "infinite_player", "infinite_bot", "spawn_grace", "hud", "exercise"]),
            ("reaction", ["aim_delay", "random_reaction", "preset_1_delay", "preset_1_jitter", "preset_1_weight", "preset_2_delay", "preset_2_jitter", "preset_2_weight", "preset_3_delay", "preset_3_jitter", "preset_3_weight"]),
            ("movement", ["speed", "strafe_rate", "jump_rate", "crouch_rate", "move_style", "ad_style", "cover_play", "ground_priors", "air_priors", "adaptive_learning"]),
        ]
        session_fields = asdict(SessionSettings()); practice_fields = asdict(PracticeSettings())
        for group, fields in groups:
            scroll = QScrollArea(); scroll.setWidgetResizable(True); content = QWidget(); content.setObjectName("SettingsContent")
            section = QVBoxLayout(content); section.setContentsMargins(4, 18, 14, 10); section.setSpacing(18)
            if group == "rules":
                presets = QHBoxLayout(); presets.setSpacing(8)
                for key in ("standard", "classic20", "classic50", "classic_unlimited"):
                    presets.addWidget(self.button(key, lambda k=key: self._rules_preset(k)))
                section.addLayout(presets)
            if group == "reaction": section.addWidget(self.label(self.t("reaction_note"), "Muted", True))
            grid = QGridLayout(); grid.setHorizontalSpacing(28); grid.setVerticalSpacing(20)
            columns = 3 if group == "reaction" else 2
            for index, name in enumerate(fields):
                control = self._control(name, name in session_fields, name in practice_fields)
                if group == "reaction" and index < 2: grid.addWidget(control, 0, index, 1, 2 if index == 1 else 1, Qt.AlignmentFlag.AlignTop)
                else:
                    offset = index - 2 if group == "reaction" else index
                    grid.addWidget(control, offset // columns + (1 if group == "reaction" else 0), offset % columns, Qt.AlignmentFlag.AlignTop)
            for index in range(columns): grid.setColumnStretch(index, 1)
            section.addLayout(grid); section.addStretch()
            scroll.setWidget(content); self.settings_tabs.addTab(scroll, self.t(group))
        inner.addWidget(self.settings_tabs, 1); outer.addWidget(frame, 1)
        bottom = QHBoxLayout(); self.dirty_label = self.label("", "Muted", True); bottom.addWidget(self.dirty_label, 1)
        bottom.addWidget(self.button("defaults", self._defaults))
        self.apply_button = self.button("apply", self._apply, True, "check"); self.apply_button.setMinimumWidth(180); self.apply_button.setToolTip(self.t("apply_note")); bottom.addWidget(self.apply_button); outer.addLayout(bottom)
        return page

    def _control(self, name, environment=False, practice=False):
        choices = {
            "ammo_policy": [(-1, self.t("map_rules")), (0, self.t("individual_ammo")), (1, self.t("infinite_ammo_both"))],
            "weapon_mode": [(0, self.t("auto_weapon")), (1, self.t("primary")), (2, self.t("secondary")), (3, self.t("melee"))],
            "move_style": [(0, self.t("mixed")), (1, self.t("circles")), (2, self.t("adad"))],
            "ad_style": [(0, self.t("mixed")), (1, self.t("wide")), (2, self.t("short")), (3, self.t("broken"))],
            "regeneration": [(0, self.t("off")), (10, "10 HP/s"), (25, "25 HP/s"), (50, "50 HP/s")],
            "exercise": [(-1, self.t("map_rules")), (0, "MGE"), (1, "Ammomod"), (2, "Endif"), (3, "Midair")],
        }
        defaults = asdict(PracticeSettings() if practice else SessionSettings() if environment else BotSettings()); value = defaults[name]
        container = QWidget(); column = QVBoxLayout(container); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(10)
        if name in choices:
            label = self.label(self.t(name), "FieldLabel"); column.addWidget(label)
            control = QComboBox(); control.setAccessibleName(self.t(name)); label.setBuddy(control)
            for key, caption in choices[name]: control.addItem(caption, key)
            control.currentIndexChanged.connect(self._edited); column.addWidget(control)
        elif type(value) is bool:
            control = Toggle(self.t(name)); control.setAccessibleName(self.t(name)); control.toggled.connect(self._edited); column.addWidget(control)
            note = {"combo": "combo_note", "switchgun": "switchgun_hint", "adaptive_learning": "adaptive_note", "ground_priors": "ground_note", "air_priors": "air_note", "cover_play": "cover_note", "shotgun_deny": "shotgun_deny_note", "quickswitch": "quickswitch_note", "shotgun_stall": "shotgun_stall_note", "spawn_grace": "spawn_grace_note", "wait_soldier": "wait_soldier_note", "infinite_player": "infinite_health_note", "infinite_bot": "infinite_health_note", "respawn_sound": "respawn_sound_note"}.get(name)
            if note: column.addWidget(self.label(self.t(note), "Muted", True))
            column.addStretch()
        else:
            limits = {"skill_step": (1, 10, 1, ""), "accuracy": (0, 100, 1, "%"),
                      "speed": (0.5, 2.0, .05, "×"), "strafe_rate": (.5, 3.0, .05, "×"),
                      "jump_rate": (0.0, 4.0, .05, "×"), "crouch_rate": (0.0, 4.0, .05, "×"),
                      "bot_hp": (1, 2000, 25, "HP"), "player_hp": (1, 2000, 25, "HP"),
                      "frag_limit": (1, 100, 1, ""), "afk_seconds": (15, 3600, 15, "s"),
                      "gravity": (200, 1200, 25, ""), "air_acceleration": (0.0, 100.0, .5, "")}
            if practice: limits[name] = (0.0, 1.0, 0.1 if name.endswith("weight") else 0.2, "" if name.endswith("weight") else "s")
            auto = -1 if name == "accuracy" else 0 if name in ("bot_hp", "player_hp", "frag_limit", "afk_seconds") else None
            label = self.t("automatic_short") if name == "accuracy" else self.t("default_short") if name.endswith("_hp") else self.t("unlimited") if name == "frag_limit" else self.t("off")
            hint = self.t("accuracy_auto_note") if name == "accuracy" else self.t("default_hp") if name.endswith("_hp") else self.t("unlimited") if name == "frag_limit" else self.t("afk_off_note")
            control = NumericControl(self.t(name), *limits[name], automatic=auto, automatic_label=label, automatic_hint=hint)
            control.setAccessibleName(self.t(name)); control.valueChanged.connect(self._edited)
            if name == "accuracy": control.setToolTip(self.t("accuracy_hint"))
            column.addWidget(control)
        control.setProperty("container", container)
        (self.practice_controls if practice else self.session_controls if environment else self.controls)[name] = control
        return container

    def _normalize_controls(self):
        old = self._loading; self._loading = True; cls = self.class_group.checkedId()
        duo = self.mode == "duo"
        for name, visible in (("gunboats", cls == 3), ("headshots_only", cls == 2)):
            self.controls[name].property("container").setVisible(visible)
            if not visible: self.controls[name].setChecked(False)
        if cls not in (3, 4) or self.controls["gunboats"].isChecked(): self.controls["switchgun"].setChecked(False)
        secondary = cls not in (5, 8) and not self.controls["gunboats"].isChecked()
        self.controls["weapon_mode"].model().item(2).setEnabled(secondary)
        if not secondary and self.controls["weapon_mode"].currentData() == 2: self.controls["weapon_mode"].setCurrentIndex(0)
        if cls not in (3, 4) and self.controls["exercise"].currentData() >= 2: self.controls["exercise"].setCurrentIndex(0)
        for index in (3, 4): self.controls["exercise"].model().item(index).setEnabled(cls in (3, 4))
        for name, control in self.controls.items():
            control.setEnabled((not duo or name == "skill_step") and (name != "switchgun" or cls in (3, 4) and not self.controls["gunboats"].isChecked()))
            visible = (not duo or name == "skill_step") and (name != "gunboats" or cls == 3) and (name != "headshots_only" or cls == 2) and (name != "switchgun" or cls in (3, 4))
            control.property("container").setVisible(visible)
        for name, control in self.practice_controls.items():
            control.setEnabled(not duo or name in ("respawn_sound", "shotgun_deny"))
            control.property("container").setVisible(not duo or name in ("respawn_sound", "shotgun_deny"))
            if name == "shotgun_deny": control.property("container").setVisible(duo or cls == 3)
            if name.startswith("preset_"): control.setEnabled(not duo and self.practice_controls["random_reaction"].isChecked())
            if name in ("quickswitch", "shotgun_stall", "wait_soldier"):
                control.property("container").setVisible(not duo and (cls == 3 or (name != "wait_soldier" and cls == 1)))
        for control in self.session_controls.values(): control.setEnabled(not duo)
        for index in range(1, self.settings_tabs.count()): self.settings_tabs.setTabEnabled(index, not duo)
        if duo: self.settings_tabs.setCurrentIndex(0)
        self.class_selector.setVisible(not duo); self.duo_note.setVisible(duo); self.host_panel.setVisible(duo)
        self.hero_class_icon.setFixedSize(96 if duo else 128, 96 if duo else 128)
        self.hero_class_icon.setPixmap(self.windowIcon().pixmap(96 if duo else 128, 96 if duo else 128))
        self.configure_button.setVisible(not duo)
        self.preset_box.setVisible(not duo); self.invite_button.setVisible(duo); self.invite_hint.setVisible(duo)
        name = (CLASSES_RU if self.language == "ru" else CLASS_NAMES).get(cls, "Soldier")
        self.setup_summary.setText(self.t("duo_rules") if duo else f'{name}  ·  {self.t("skill_step")} {self.controls["skill_step"].value()} / 10')
        self._loading = old

    def _set_mode(self, mode):
        if self._loading or mode == self.mode: return
        self.mode = mode
        for key, button in self.mode_buttons.items(): button.setChecked(key == mode)
        self._normalize_controls(); self._render_arenas(); self.set_connection_state(self.connection_stage, self.connection_detail)
        self.show_snapshot(self.last_snapshot); self._save_preferences(); self.mark_dirty()
        if self.motion and not self.demo:
            if hasattr(self, "mode_animation"): self.mode_animation.stop()
            effect = QGraphicsOpacityEffect(self.pages.currentWidget()); self.pages.currentWidget().setGraphicsEffect(effect)
            self.mode_animation = QPropertyAnimation(effect, b"opacity", self)
            self.mode_animation.setStartValue(.82); self.mode_animation.setEndValue(1.0); self.mode_animation.setDuration(180)
            self.mode_animation.setEasingCurve(QEasingCurve.Type.OutExpo); self.mode_animation.start()

    def _host_changed(self):
        if self._loading: return
        self.host_class = self.host_class_box.currentData(); self.visibility = self.visibility_box.currentData()
        self._save_preferences(); self.mark_dirty()

    def _invite_friend(self):
        if self.demo: return
        QDesktopServices.openUrl(QUrl("steam://open/friends"))
        self.notify(self.t("invite_note"))

    def _rules_preset(self, name):
        from dataclasses import replace
        settings = self.settings(); practice = self.practice_settings()
        if name == "standard":
            settings = replace(settings, player_hp=0, bot_hp=0, exercise=-1, frag_limit=20, bot_ammo=False, player_ammo=False, crits=False, regeneration=0)
            practice = replace(practice, ammo_policy=-1, infinite_player=False, infinite_bot=False)
        else:
            settings = replace(settings, player_hp=300, bot_hp=300, exercise=1, frag_limit={"classic20":20,"classic50":50,"classic_unlimited":0}[name], bot_ammo=False, player_ammo=False, crits=False, regeneration=0)
            practice = replace(practice, ammo_policy=0, infinite_player=False, infinite_bot=False)
        self.set_settings(settings); self.set_practice_settings(practice); self.mark_dirty()

    def _edited(self, *args):
        if self._loading: return
        self._normalize_controls(); self.mark_dirty(True)

    def settings(self):
        values = asdict(self._base_settings); values.update(bot_class=self.class_group.checkedId(), combo=False, mimic=False, hit_sound=False)
        for name, control in self.controls.items():
            values[name] = control.currentData() if isinstance(control, QComboBox) else control.isChecked() if isinstance(control, Toggle) else control.value()
        return BotSettings.parse(values)

    def session_settings(self):
        return SessionSettings.parse({**asdict(self._session_settings), **{name: control.isChecked() if isinstance(control, Toggle) else control.value() for name, control in self.session_controls.items()}})

    def set_settings(self, settings):
        self._base_settings = settings
        previous = self._loading; self._loading = True
        self.class_buttons[settings.bot_class].setChecked(True)
        for name, value in asdict(settings).items():
            if name not in self.controls: continue
            control = self.controls[name]
            if isinstance(control, QComboBox): control.setCurrentIndex(control.findData(value))
            elif isinstance(control, Toggle): control.setChecked(value)
            else: control.setValue(value)
        self._normalize_controls(); self._loading = previous

    def set_session_settings(self, settings):
        self._session_settings = settings
        previous = self._loading; self._loading = True
        for name, value in asdict(settings).items():
            if name not in self.session_controls: continue
            control = self.session_controls[name]
            if isinstance(control, Toggle): control.setChecked(value)
            else: control.setValue(value)
        self._loading = previous

    def practice_settings(self):
        return PracticeSettings.parse({name: control.currentData() if isinstance(control, QComboBox) else control.isChecked() if isinstance(control, Toggle) else control.value() for name, control in self.practice_controls.items()})

    def set_practice_settings(self, settings):
        previous = self._loading; self._loading = True
        for name, value in asdict(settings).items():
            control = self.practice_controls[name]
            if isinstance(control, QComboBox): control.setCurrentIndex(control.findData(value))
            elif isinstance(control, Toggle): control.setChecked(value)
            else: control.setValue(value)
        self._normalize_controls(); self._loading = previous

    def _defaults(self):
        self.set_settings(BotSettings()); self.set_session_settings(SessionSettings()); self.set_practice_settings(PracticeSettings()); self.mark_dirty()

    def mark_dirty(self, dirty=True):
        self.dirty = dirty
        self.dirty_label.setText(self.t("dirty" if self.online else "dirty_offline") if dirty else self.t("settings_ready"))
        self._update_actions()

    def set_connection_state(self, stage, detail=""):
        if stage == "idle" and not self.install_ready:
            stage = "not_installed" if self.game_directory else "missing_game"
        self.connection_stage = stage; self.connection_detail = detail
        self.online = stage == "connected"
        key = "state_" + stage
        caption = self.t(key)
        self.connection_status.setText(self.t("demo_status") if self.demo else caption)
        self.stage_label.setText(caption); self.stage_label.setToolTip(detail)
        self.hero_title.setText(self.t("hero_duo" if self.mode == "duo" else "hero_ready" if self.install_ready else "hero_install"))
        self.hero_description.setText(self.t("hero_duo_note" if self.mode == "duo" else "hero_ready_note" if self.install_ready else "hero_install_note"))
        self.folder_label.setText(self.t("game_found") if self.game_directory else self.t("find_game"))
        self.folder_label.setToolTip(self.game_directory)
        self.mark_dirty(self.dirty)

    def set_online(self, online):
        self.set_connection_state("connected" if online else "idle")

    def _update_actions(self):


        available = not self.busy and not self.action_busy
        active = self.online and bool(self.last_snapshot.get("active") or self.last_snapshot.get("team", {}).get("hosting"))
        label = "connecting" if self.launch_pending else ("host_duo" if self.mode == "duo" else "start_main") if self.install_ready else "install_main"
        self.main_button.setText(self.t(label)); self.main_button.symbol = "play" if self.install_ready else "download"
        self.main_button.setVisible(not active)
        self.main_button.setEnabled(available and not self.launch_pending and self.connection_stage != "checking")
        self.main_button.update()
        self.apply_button.setEnabled(available and self.online and self.dirty)
        self.stop_button.setEnabled(available and active)
        self.new_duel_button.setEnabled(available and self.online)
        self.new_duel_button.setVisible(self.online)
        self.stop_button.setVisible(active)
        self.visibility_box.setEnabled(available and not self.online)
        team = self.last_snapshot.get("team") or {}
        waiting = self.mode == "duo" and self.online and bool(team.get("hosting") and team.get("waiting"))
        self.teammate_button.setVisible(waiting)
        self.teammate_button.setEnabled(available and waiting and not team.get("pending_bot"))
        self.invite_button.setVisible(self.mode == "duo" and not team.get("teammate_bot"))
        self.invite_hint.setVisible(self.mode == "duo" and not team.get("teammate_bot"))
        self.invite_button.setEnabled(available and waiting and not team.get("pending_bot"))

    def set_action_busy(self, busy):
        self.action_busy = busy; self._update_actions()

    def set_launch_pending(self, pending):
        self.launch_pending = pending; self._update_actions()

    def set_busy(self, busy):
        self.busy = busy; self.cancel_button.setVisible(busy); self.progress.setVisible(busy); self._update_actions()
        if not busy and self._closing: self.close()

    def install_progress(self, phase, current, total):
        name = {"sourcemod": "SourceMod", "metamod-source": "MetaMod:Source", "Install": self.t("write_files")}.get(phase, phase)
        self.stage_label.setText(self.t("installation_busy") + " " + name)
        self.progress.setRange(0, 100 if total else 0)
        if total: self.progress.setValue(current * 100 // total)

    def set_arenas(self, arenas):
        if arenas == self.arenas and self.arena_box.count(): return
        self.arenas = arenas; self._render_arenas()

    def _render_arenas(self):
        current = self.arena_box.currentData() or self.preferences.get("arena")
        self.arena_box.clear()
        for arena in self.arenas:
            if self.mode == "duo" and not arena.get("duo", False): continue
            self.arena_box.addItem(arena["name"], arena["id"])
        if not self.arena_box.count(): self.arena_box.addItem(self.t("arena_pending"), 0)
        index = self.arena_box.findData(current)
        if index >= 0: self.arena_box.setCurrentIndex(index)

    def show_snapshot(self, snapshot):
        self.last_snapshot = snapshot; active = bool(snapshot.get("active")); session = snapshot.get("session") or {}
        team = snapshot.get("team") or {}; duo = self.mode == "duo"; hosted = bool(team.get("hosting"))
        self.player_label.setText(snapshot.get("name") or self.t("player"))
        score = team if hosted else session
        self.score.setText(f'{score.get("player_score", 0)} : {score.get("bot_score", 0)}' if active or hosted else "— : —")
        self.session_empty.setVisible(not active and not hosted)
        self.session_empty.setText(self.t("duo_empty" if duo else "no_session"))
        self.player_label.setVisible(active or hosted); self.health_widget.setVisible(active or hosted)
        self.decision_label.setVisible(active and not duo)
        for who in ("player", "bot"):
            self.health_bars[who].setVisible(not duo); self.live_labels[who + "_hp"].setVisible(not duo)
            hp = max(0, session.get(who + "_hp", 0)); maximum = max(1, session.get(who + "_max_hp", 1))
            self.live_labels[who + "_hp"].setText(self.t(who) + f" · {hp} HP")
            self.health_bars[who].setValue(min(100, round(hp * 100 / maximum)) if active else 0)
        self.team_label.setVisible(duo)
        self.team_label.setText((self.t("adding_bot_teammate" if team.get("pending_bot") else "waiting_partner") if team.get("waiting") else self.t("bot_teammate" if team.get("teammate_bot") else "partner") + ": " + team.get("partner_name", "")) + "\n" + self.t("duo_rules") if hosted else self.t("duo_team_preview"))
        if hosted and team.get("phase") in ("fighting", "intermission"):
            status = self.t("duo_round_wait") if team["phase"] == "intermission" else self.t("duo_round_live").format(round=team.get("round", 1), ours=team.get("alive_team", 0), theirs=team.get("alive_opponents", 0))
            if team.get("player_out") and team["phase"] == "fighting": status += "\n" + self.t("duo_round_out")
            self.team_label.setText(self.team_label.text() + "\n" + status)
        decision = snapshot.get("decision") or {}
        self.decision_label.setText(self.t("plan_" + decision.get("goal", "waiting")) if active else self.t("plan_waiting"))
        self._update_actions()

    def load_presets(self):
        previous = self._loading; self._loading = True
        self.preset_box.clear(); self.preset_box.addItem(self.t("custom"), None)
        try:
            self.presets = self.store.list()
            for preset in self.presets: self.preset_box.addItem(preset.name, preset.id)
            self.preset_box.setCurrentIndex(max(0, self.preset_box.findData(self.current_preset)))
        except (OSError, ValueError) as error:
            self.presets = []; self.notify(str(error), True)
        self._loading = previous

    def _choose_preset(self):
        if self._loading: return
        self.current_preset = self.preset_box.currentData()
        found = next((p for p in self.presets if p.id == self.current_preset), None)
        if found:
            self.set_settings(found.settings); self.set_session_settings(found.session_settings); self.set_practice_settings(found.practice_settings); self.mark_dirty()
        self._save_preferences()

    def _save_preset(self, save_as=False):
        current = next((p for p in self.presets if p.id == self.current_preset), None)
        name = current.name if current and not save_as else ""
        if not name:
            name, ok = QInputDialog.getText(self, self.t("save"), self.t("preset_name"))
            if not ok: return
        try:
            saved = self.store.save(name, self.settings(), current.id if current and not save_as else None, self.session_settings(), self.practice_settings())
            self.current_preset = saved.id; self.load_presets(); self._save_preferences(); self.notify(self.t("saved"))
        except (OSError, ValueError) as error: self.notify(str(error), True)

    def _rename_preset(self):
        current = next((p for p in self.presets if p.id == self.current_preset), None)
        if not current: return
        name, ok = QInputDialog.getText(self, self.t("rename"), self.t("preset_name"), text=current.name)
        if ok:
            try: self.store.save(name, current.settings, current.id, current.session_settings, current.practice_settings); self.load_presets()
            except (OSError, ValueError) as error: self.notify(str(error), True)

    def _delete_preset(self):
        if not self.current_preset: return
        if QMessageBox.question(self, self.t("delete"), self.t("delete_preset_question")) == QMessageBox.StandardButton.Yes:
            self.store.delete(self.current_preset); self.current_preset = None; self.load_presets(); self._save_preferences()

    def _import_preset(self):
        name, _ = QFileDialog.getOpenFileName(self, self.t("import"), str(Path.home()), "mgebot preset (*.json)")
        if not name: return
        try:
            preset = self.store.import_file(Path(name)); self.current_preset = preset.id; self.load_presets()
            self.set_settings(preset.settings); self.set_session_settings(preset.session_settings); self.set_practice_settings(preset.practice_settings); self.mark_dirty(); self._save_preferences()
        except (OSError, ValueError) as error: self.notify(str(error), True)

    def _export_preset(self):
        current = next((p for p in self.presets if p.id == self.current_preset), None)
        if not current:
            self._save_preset(True); current = next((p for p in self.presets if p.id == self.current_preset), None)
        if not current: return
        name, _ = QFileDialog.getSaveFileName(self, self.t("export"), str(Path.home() / "mgebot-preset.json"), "mgebot preset (*.json)")
        if name:
            try: self.store.export_file(Preset(current.id, current.name, self.settings(), self.session_settings(), self.practice_settings()), Path(name))
            except (OSError, ValueError) as error: self.notify(str(error), True)

    def _launch(self):
        if self.demo: return
        try: self.launch_requested.emit(self.settings(), int(self.arena_box.currentData() or 0))
        except ValueError as error: self.notify(str(error), True)

    def _apply(self):
        if self.demo or not self.online or not self.dirty: return
        try: self.apply_requested.emit(self.settings())
        except ValueError as error: self.notify(str(error), True)

    def _player_menu(self, point):
        steam = self.last_snapshot.get("steamid", "")
        if not steam.isdigit() or len(steam) != 17: return
        menu = QMenu(self); menu.addAction(self.t("copy_id"), lambda: QApplication.clipboard().setText(steam)); menu.exec(self.player_label.mapToGlobal(point))

    def _change_language(self):
        if self._loading: return
        draft, environment, page, tab, arena, dirty = self.settings(), self.session_settings(), self.pages.currentIndex(), self.settings_tabs.currentIndex(), self.arena_box.currentData(), self.dirty
        practice = self.practice_settings()
        self.language = self.language_box.currentData(); self._save_preferences(); self._build(draft, environment, practice)
        self._select_page(page); self.settings_tabs.setCurrentIndex(tab); self.arena_box.setCurrentIndex(max(0, self.arena_box.findData(arena))); self.mark_dirty(dirty)

    def _save_preferences(self):
        self.preferences.update(language=self.language, motion=self.motion, tf_directory=self.game_directory,
                                preset=self.current_preset, arena=self.arena_box.currentData(), mode=self.mode, visibility=self.visibility, host_class=self.host_class)
        write_json(self.data / "ui.json", self.preferences)

    def _preferences(self):
        dialog = QDialog(self); dialog.setWindowTitle(self.t("app_settings")); dialog.setMinimumWidth(560)
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        layout = QVBoxLayout(dialog); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(16)
        titlebar = WindowBar(); title = QHBoxLayout(titlebar); title.setContentsMargins(0, 0, 0, 0)
        title.addWidget(self.label(self.t("app_settings"), "Section"), 1)
        close = ActionButton("", "close"); close.setFixedWidth(36); close.setAccessibleName(self.t("close")); close.clicked.connect(dialog.reject); title.addWidget(close); layout.addWidget(titlebar)
        motion = Toggle(self.t("motion")); motion.setChecked(self.motion); layout.addWidget(motion)
        layout.addWidget(self.label(self.t("game_folder"), "Muted"))
        path = QLineEdit(self.game_directory); path.setAccessibleName(self.t("game_folder")); row = QHBoxLayout(); row.addWidget(path, 1)
        browse = self.button("browse"); browse.clicked.connect(lambda: self._pick_directory(path)); row.addWidget(browse); layout.addLayout(row)
        logs = self.button("crash_logs", self._open_crash_logs, symbol="folder"); layout.addWidget(logs, 0, Qt.AlignmentFlag.AlignLeft)
        row = QHBoxLayout(); repair = self.button("repair", symbol="download"); repair.clicked.connect(lambda: (dialog.accept(), self.install_requested.emit(path.text(), self.payload))); row.addWidget(repair)
        row.addStretch(); save = self.button("save", primary=True); row.addWidget(save); layout.addLayout(row)
        def accepted():
            changed = path.text() != self.game_directory; self.game_directory = path.text(); self.motion = motion.isChecked(); self._save_preferences(); dialog.accept()
            if changed: self.directory_changed.emit(self.game_directory)
        save.clicked.connect(accepted); dialog.exec()

    def _open_crash_logs(self):
        folder = self.data / "crashlogs"; folder.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve()))):
            self.notify(str(folder), True)

    def _pick_directory(self, edit=None):
        selected = QFileDialog.getExistingDirectory(self, self.t("game_folder"), self.game_directory or str(Path.home()))
        if selected:
            if edit: edit.setText(selected)
            else: self.game_directory = selected; self._save_preferences(); self.directory_changed.emit(selected)
        return selected

    def notify(self, message, error=False):
        self.message.setObjectName("Error" if error else "Message"); self.message.setText(message)
        self.message.style().unpolish(self.message); self.message.style().polish(self.message); self.message.show()
        if not error: QTimer.singleShot(7000, self.message.hide)

    def closeEvent(self, event):
        if self.busy:
            self._closing = True; self.cancel_requested.emit(); event.ignore()
        else:
            self._save_preferences(); event.accept()
