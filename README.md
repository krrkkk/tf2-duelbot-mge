english · [русский](README.ru.md)

# mgebot duel

local TF2 training by avxgroup. install it, pick a bot, play.

## get started

1. unpack the whole release. open `mgebot-duel.exe` on windows or `./mgebot-duel` on linux.
2. hit **install**. the map and plugin are included; SourceMod and MetaMod download automatically.
3. pick an arena and hit **start**.
4. tune the bot in **bots**, then hit **apply**. presets can be saved and shared.

already playing a local game with `-insecure`? the app connects to that game.
for normal secured servers, restart TF2 without `-insecure`.

## what's here

- bot class, difficulty, accuracy, weapons and movement settings.
- **auto** or a clear percentage slider for accuracy. actual hits still depend on dodging and projectile travel.
- live score, hp, damage, the bot's current plan and learning updates.
- session history, win rate and damage per minute.
- shared learning for the bots on your computer. nothing gets uploaded.

linux build: native TF2, x86_64, glibc 2.28+. for Proton, use the windows package.

## your files

presets: `%LOCALAPPDATA%/mgebot-duel` on windows, `~/.local/share/mgebot-duel` on linux (`XDG_DATA_HOME` also works).

history and learning: `tf/addons/sourcemod/data/sqlite/`.
arena edits: `tf/addons/sourcemod/configs/botduel_editor/`.
updates keep these files. don't share `connection.json` or `mgebot_companion.cfg`: they contain local connection details.

## crash logs

settings → **TF2 crash logs**. files are in the app's data folder, under `crashlogs/`.
the recorder keeps up to 10 reports: process exit codes, long stalls, recent console/SourceMod logs and matching dumps if TF2 created them.
it keeps watching until TF2 exits, even if you close the app. nothing is uploaded.

## source and builds

Python 3.12+. install `requirements.txt`, then run `python run.py`.
a source checkout needs the matching plugin package via `--payload path/to/package.zip`; ready releases already include it.

```sh
python scripts/build.py --platform windows --out build/windows --cache build/cache --payload mgebot_duel_5.1.2_Windows_x64.zip
python scripts/build.py --platform linux --out build/linux --cache build/cache --payload mgebot_duel_5.1.2_Linux_x64.zip
python scripts/package.py --out dist --build build/windows --build build/linux
```

windows builds need MinGW-w64; linux builds need `dpkg-deb`. Python and Qt are bundled in the finished app.
the bot's private SourcePawn code is not included.

[changes](CHANGELOG.md) · [license](LICENSE) · [credits](THIRD_PARTY.md)
