## 0.3.5

- Public Windows release with plugin 5.2.4.
- Refreshed English and Russian installation instructions. Local crash reports remain available in App settings.

## 0.3.4

- Team elimination rounds, shared respawns and arena-list joining for 2v2.
- Deferred arena placement fixes the black-room spawn after desktop launch.
- Exclude the broken Triumph Spire spawn on all three copies.
- Direct bot options, saved air-deny switch, clearer labels and cosmetic recovery after a win.

## 0.3.3

- Plugin 5.2.3 fixes Windows x64 pointer truncation in bot spread seed initialization. The old computed address exactly matches the access violation from the operator dump.
- Keeps the bot teammate, settings, models and previous startup mitigations. Close TF2 before updating.

## 0.3.2

- Plugin 5.2.2: optional AI teammate in 2v2, one human plus three independently controlled bots.
- Add teammate action in the waiting room and the in-game menu; distinct classes and shared score to 20.
- Includes the 0.3.1 crash mitigations below. Actual Windows crash resolution is still unconfirmed.

## 0.3.1

- Plugin 5.2.1: staged 2v2 startup and safe wearable origins.
- Local co-op skips optional bot cosmetics while the Windows crash is investigated.
- Installing over a running TF2 process is refused, including legacy live-update calls.

## 0.3.0

- Supplied logo in the window, app reveal and executable icon.
- Local 2v2 hosting through Steam Networking; friends-only by default.
- Current practice controls and versioned preset migration.
- Statistics page and history polling removed; stored data preserved.
- Original MGE respawn sound toggle.
- Windows application only; Linux dedicated plugin is distributed separately.

# 0.2.3

- optional operator steam sign-in.
- area selection, screenshot comments and a separate feedback journal.
- search, open/done, screenshots and copying notes.
- normal training still works without an account.

english · [русский](CHANGELOG.ru.md)

# changes

## 0.2.2

- fixed the class icon and text drifting away from the left edge.
- corrected the install/start status when setup still needs an update.

## 0.2.1

- class icon moved left; the return-to-game button is gone during a duel.
- shorter switchgun label.
- removed the plugin's extra hit sound. your TF2 sound settings stay yours.
- local status goes directly between plugins, without console spam.
- app launches skip the arena menu and waiting-for-players countdown.
- the bot waits 5 seconds in the first app-started duel only.
- local reports for exits and hangs, with recent logs and matching dumps when available.

## 0.2.0

- WLogs-style interface, custom window bar and a short opening animation.
- english by default. one main button: install → start.
- no archive picker in the normal install flow.
- local game connection no longer depends on TCP RCON.
- connects to an existing compatible game; shows why a connection is waiting.
- accuracy has separate auto/manual modes, a slider and a numeric field.
- more behavior settings, preset rename/delete, live bot plans and learning counters.
- english and russian docs are now short and included in every package.

## 0.1.0

first release: installation, bot settings, presets and local session history.
