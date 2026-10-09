from __future__ import annotations

import math
import re
import uuid
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .storage import read_json, write_json

CLASS_NAMES = {1: "Scout", 3: "Soldier", 7: "Pyro", 4: "Demoman", 6: "Heavy", 9: "Engineer", 5: "Medic", 2: "Sniper", 8: "Spy"}


@dataclass(frozen=True)
class SessionSettings:
    adaptive_learning: bool = True
    ground_priors: bool = True
    air_priors: bool = True
    cover_play: bool = True
    afk_seconds: int = 180
    gravity: int = 800
    air_acceleration: float = 10.0

    @classmethod
    def parse(cls, data: Any) -> "SessionSettings":
        defaults = asdict(cls())
        if not isinstance(data, dict) or set(data) - set(defaults):
            raise ValueError("Unsupported local-session fields")
        for name, value in data.items():
            kind = type(defaults[name])
            if kind is float:
                if type(value) not in (float, int) or not math.isfinite(value):
                    raise ValueError(f"Invalid session setting: {name}")
                value = float(value)
            elif type(value) is not kind:
                raise ValueError(f"Invalid session setting: {name}")
            defaults[name] = value
        result = cls(**defaults)
        if not 0 <= result.afk_seconds <= 3600 or not 200 <= result.gravity <= 1200 or not 0 <= result.air_acceleration <= 100:
            raise ValueError("Session setting is outside the allowed range")
        return result

    def to_keyvalues(self) -> str:
        checked = self.parse(asdict(self))
        lines = ['"MGBotSession"', "{", '    "version" "1"']
        for name, value in asdict(checked).items():
            lines.append(f'    "{name}" "{int(value) if isinstance(value, bool) else value}"')
        return "\n".join(lines + ["}", ""])


@dataclass(frozen=True)
class BotSettings:
    bot_class: int = 3
    skill_step: int = 5
    combo: bool = False
    accuracy: int = -1
    weapon_mode: int = 0
    switchgun: bool = False
    gunboats: bool = False
    headshots_only: bool = False
    speed: float = 1.0
    strafe_rate: float = 1.0
    move_style: int = 0
    ad_style: int = 0
    jump_rate: float = 1.0
    crouch_rate: float = 1.0
    mimic: bool = False
    bot_ammo: bool = False
    player_ammo: bool = False
    bot_hp: int = 0
    player_hp: int = 0
    crits: bool = False
    regeneration: int = 0
    fall_protection: bool = False
    exercise: int = -1
    frag_limit: int = 20
    hud: bool = True
    hit_sound: bool = False

    @classmethod
    def parse(cls, data: Any) -> "BotSettings":
        if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
            raise ValueError("Unsupported preset fields")
        defaults = asdict(cls())
        for name, value in data.items():
            expected = type(defaults[name])
            if expected is float:
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"Invalid number: {name}")
                value = float(value)
            elif type(value) is not expected:
                raise ValueError(f"Invalid value type: {name}")
            defaults[name] = value
        defaults["hit_sound"] = False
        result = cls(**defaults)
        limits = {
            "bot_class": (1, 9), "skill_step": (1, 10), "accuracy": (-1, 100),
            "weapon_mode": (0, 3), "speed": (0.5, 2.0), "strafe_rate": (0.5, 3.0),
            "move_style": (0, 2), "ad_style": (0, 3), "jump_rate": (0.0, 4.0),
            "crouch_rate": (0.0, 4.0), "bot_hp": (0, 2000), "player_hp": (0, 2000),
            "exercise": (-1, 3), "frag_limit": (0, 100),
        }
        for name, (low, high) in limits.items():
            if not low <= getattr(result, name) <= high:
                raise ValueError(f"{name}: expected {low}…{high}")
        if result.regeneration not in (0, 10, 25, 50):
            raise ValueError("Unsupported regeneration rate")
        if result.switchgun and (result.bot_class not in (3, 4) or result.gunboats):
            raise ValueError("Switchgun requires Soldier without Gunboats, or Demoman")
        if result.gunboats and result.bot_class != 3:
            raise ValueError("Gunboats require Soldier")
        if result.headshots_only and result.bot_class != 2:
            raise ValueError("Headshots-only requires Sniper")
        if result.weapon_mode == 2 and (result.bot_class in (5, 8) or result.gunboats):
            raise ValueError("This class has no offensive secondary in this loadout")
        if result.combo and result.skill_step != 10:
            raise ValueError("Combo uses difficulty 10")
        if result.exercise >= 2 and result.bot_class not in (3, 4):
            raise ValueError("This exercise requires Soldier or Demoman")
        return result

    def to_keyvalues(self) -> str:
        checked = self.parse(asdict(self))
        lines = ['"MGBotLocalPreset"', "{", '    "version" "1"']
        for name, value in asdict(checked).items():
            text = str(int(value)) if isinstance(value, bool) else str(value)
            lines.append(f'    "{name}" "{text}"')
        return "\n".join(lines + ["}", ""])


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    settings: BotSettings
    session_settings: SessionSettings = SessionSettings()

    @classmethod
    def parse(cls, data: Any) -> "Preset":
        if not isinstance(data, dict) or data.get("version") not in (1, 2):
            raise ValueError("Unsupported preset format")
        expected = {"version", "id", "name", "settings"}
        if data["version"] == 2:
            expected.add("session_settings")
        if set(data) != expected:
            raise ValueError("Unsupported preset fields")
        if not isinstance(data["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", data["id"]):
            raise ValueError("Invalid preset identifier")
        name = data["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise ValueError("Preset name must contain 1–80 printable characters")
        return cls(data["id"], name.strip(), BotSettings.parse(data["settings"]), SessionSettings.parse(data.get("session_settings", {})))

    def document(self) -> dict[str, Any]:
        return {"version": 2, "id": self.id, "name": self.name, "settings": asdict(self.settings), "session_settings": asdict(self.session_settings)}


class PresetStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def list(self) -> list[Preset]:
        if not self.directory.exists():
            return []
        return sorted((Preset.parse(read_json(p)) for p in self.directory.glob("*.json")), key=lambda p: p.name.casefold())

    def save(self, name: str, settings: BotSettings, identifier: str | None = None,
             session_settings: SessionSettings | None = None) -> Preset:
        p = Preset.parse({"version": 2, "id": identifier or uuid.uuid4().hex, "name": name, "settings": asdict(settings),
                          "session_settings": asdict(session_settings or SessionSettings())})
        write_json(self.directory / (p.id + ".json"), p.document())
        return p

    def import_file(self, path: Path) -> Preset:
        imported = Preset.parse(read_json(path))

        return self.save(imported.name, imported.settings, session_settings=imported.session_settings)

    def export_file(self, preset: Preset, path: Path) -> None:
        write_json(path, Preset.parse(preset.document()).document())

    def delete(self, identifier: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Invalid preset identifier")
        (self.directory / (identifier + ".json")).unlink(missing_ok=True)
