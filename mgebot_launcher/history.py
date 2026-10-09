from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


def read_sessions(tf_directory: Path, limit: int = 200) -> list[dict[str, Any]]:
    path = tf_directory / "addons/sourcemod/data/sqlite/botduel.sq3"
    if not path.is_file():
        return []
    if not 1 <= limit <= 1000:
        raise ValueError("Invalid history limit")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='botduel_sessions'").fetchall()
        if not tables:
            return []
        rows = connection.execute("SELECT id,steamid,name,started,ended,status,reason,map,arena,profile,modified,player_score,bot_score,active_seconds,damage_out,damage_in,hits,airshots FROM botduel_sessions ORDER BY started DESC,id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


def totals(sessions: list[dict[str, Any]]) -> dict[str, int | float]:
    completed = [s for s in sessions if s["status"] == "completed"]
    seconds = sum(max(0.0, float(s["active_seconds"])) for s in sessions)
    damage = sum(max(0, int(s["damage_out"])) for s in sessions)
    return {"sessions": len(sessions), "completed": len(completed), "seconds": seconds,
            "damage_out": damage, "damage_in": sum(max(0, int(s["damage_in"])) for s in sessions),
            "player_score": sum(max(0, int(s["player_score"])) for s in sessions),
            "bot_score": sum(max(0, int(s["bot_score"])) for s in sessions),
            "dpm": damage * 60 / seconds if seconds else 0.0}
