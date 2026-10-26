# mgebot duel companion 0.3.7

[Русский](README.ru.md) · [Changes](CHANGELOG.md) · [Discord: installation, updates and support](https://discord.gg/GGMz952jBA)

sourcemod version needed - 1.13.0.7441

## Start playing

1. Install TF2 through Steam and close the game before installing or updating components.
2. Extract the **entire** `mgebot_duel_companion_0.3.7_Windows_x64.zip` and run `mgebot-duel.exe` inside it. Keep the adjacent folders with the executable.
3. Select your TF2 folder if it is not detected, then choose **Install**. The app downloads the pinned MetaMod and SourceMod dependencies on the first installation.
4. Choose **1v1** or **2v2**, an arena and bot settings, then start.

When upgrading the app, extract it to a new folder and update the game components with TF2 closed. Your saved presets, player databases and arena edits are preserved. Python does not need to be installed for the portable app.

Launch TF2 through this app for practice. Exit the game and restart it through Steam before joining regular servers.

## 2v2

The app hosts the game on your computer through Steam Networking. **Friends Only** is the default; Unlisted and Listed are also available before launch. Invite your friend through Steam. They need the same selected map; after connecting, they use `!add`, choose 2v2 and select your arena. Full arenas have a queue.

You can also select **Add an AI teammate** to play with a bot against two bots. Scout, Soldier and Demoman are allowed, with no duplicate class within a team. Bot classes are random. A team scores only after eliminating both opponents; everyone respawns together for the next round. First to **20 round wins**. Keep TF2 open while hosting.

## Training

Tactics, shotgun air deny, switchgun and Gunboats are available directly in the bot setup. Extra settings cover reaction delay, movement, spawn protection and other training rules. Classic Ammomod has starting 300 HP and finite ammunition. Original MGE respawn audio has its own switch. Save presets and use **Apply** to change a running session.

The app has no operator sign-in, screenshot submission or feedback journal. Alt+Shift+A is not registered. Crash diagnostics remain local: **App settings → TF2 crash logs** opens the folder; the app does not automatically upload reports or dumps. Presets and game connection data stay on your computer.

## Release notes

- Windows x64 app only. Linux users use the separate **Linux Dedicated** plugin archive with their own TF2 server.
- `!hop` needs a compatible optional RIPExt extension. The Windows local-practice bundle does not install it; the Linux dedicated archive includes it.
- The plugin includes the Windows address fix and the 2v2 arena/round fixes. Full gameplay and Steam friend joining on the previously affected Windows PC still need confirmation. 

## Source and build

The source archive contains the companion app and its build scripts. Bot SourcePawn source and personal data are not included. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY.md).

With Python 3.13, install `requirements.txt`, then run:

```sh
python run.py --payload /path/to/mgebot_duel_5.3.1_Windows_x64.zip
```

To create a Windows portable bundle, install MinGW-w64 with `gcc` and `windres` and run:

```sh
python scripts/build.py --platform windows --out build/windows --cache build/cache --payload /path/to/mgebot_duel_5.3.1_Windows_x64.zip
python scripts/package.py --out dist --build build/windows
```

The build verifies pinned downloads from `build-lock.json`; the package records hashes and requires the source to match the built app. `SHA256SUMS.txt` accompanies release assets.
