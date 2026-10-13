from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import unittest
from mgebot_launcher.presets import BotSettings, PracticeSettings, Preset, PresetStore
from mgebot_launcher.steam import GameProcess, hosting_config, hosting_matches, launch_training


class PracticeCase(TestCase):
    def test_deny_preference_migrates_and_rejects_non_boolean_values(self):
        self.assertTrue(PracticeSettings.parse({'respawn_sound':False}).shotgun_deny)
        value=PracticeSettings.parse({'shotgun_deny':False})
        self.assertIn('"shotgun_deny" "0"',value.to_keyvalues())
        with self.assertRaises(ValueError):PracticeSettings.parse({'shotgun_deny':0})

    def test_existing_presets_migrate_and_export_current_settings(self):
        legacy = {"version": 1, "id": "a" * 32, "name": "My preset", "settings": asdict(BotSettings())}
        loaded = Preset.parse(legacy)
        self.assertEqual(loaded.practice_settings, PracticeSettings())
        practice = replace(loaded.practice_settings, aim_delay=.8, random_reaction=True, preset_1_weight=0., respawn_sound=False)
        with TemporaryDirectory() as tmp:
            store = PresetStore(Path(tmp)); saved = store.save(loaded.name, loaded.settings, practice_settings=practice)
            exported = Path(tmp) / 'export.json'; store.export_file(saved, exported)
            imported = store.import_file(exported)
            self.assertEqual(imported.practice_settings, practice)
            self.assertNotEqual(imported.id, saved.id)
            self.assertNotIn('token', exported.read_text())

    def test_running_game_cannot_receive_even_a_legacy_live_plugin_update(self):
        import threading
        from mgebot_launcher.installer import Installer
        with TemporaryDirectory() as tmp:
            root = Path(tmp); tf = root / 'tf'; tf.mkdir()
            (tf / 'gameinfo.txt').write_text('Team Fortress 2 SteamAppId 440')
            installer = Installer(root / 'app', {}, process_check=lambda: True)
            with self.assertRaisesRegex(RuntimeError, 'live plugin replacement is disabled'):
                installer.install(tf, root / 'unused.zip', 'windows', lambda *args: None, threading.Event(), allow_running_local=True)
            self.assertFalse((root / 'app').exists())

    def test_invalid_numeric_values_and_class_rejected_before_game_request(self):
        for value in (float('nan'), float('inf'), -.2, 1.2, .3, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PracticeSettings.parse({'aim_delay': value})
        for name, value in [('quickswitch', 1), ('ammo_policy', 2), ('preset_2_weight', .35), ('unknown', 0)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                PracticeSettings.parse({name: value})
        with self.assertRaises(ValueError): PracticeSettings().to_keyvalues(2)
        self.assertIn('"aim_delay" "0.8"', replace(PracticeSettings(), aim_delay=.8).to_keyvalues(4))

    def test_visibility_has_explicit_steam_and_listing_policy(self):
        self.assertIn(b'sv_use_steam_networking 1', hosting_config('friends'))
        self.assertIn(b'sv_friends_only 1', hosting_config('friends'))
        self.assertIn(b'sv_allow_server_adverisement_to_master_server 0', hosting_config('friends'))
        self.assertIn(b'sv_friends_only 0', hosting_config('unlisted'))
        self.assertIn(b'sv_allow_server_adverisement_to_master_server 1', hosting_config('listed'))
        self.assertIn(b'sv_use_steam_networking 0', hosting_config('local'))
        with self.assertRaises(ValueError): hosting_config('friends;quit')

    def test_room_creation_waits_for_confirmed_network_policy(self):
        self.assertFalse(hosting_matches('friends', {}))
        self.assertFalse(hosting_matches('friends', {'lan': True, 'steam_networking': False}))
        confirmed = {'lan': False, 'steam_networking': True, 'friends_only': True, 'listed': False}
        self.assertTrue(hosting_matches('friends', confirmed))
        self.assertFalse(hosting_matches('listed', confirmed))
        self.assertFalse(hosting_matches('friends', dict(confirmed, steam_networking='true')))

    def test_network_options_precede_map_and_loopback_is_not_forced(self):
        with TemporaryDirectory() as tmp:
            tf = Path(tmp) / 'tf'; (tf/'cfg').mkdir(parents=True)
            with mock.patch('mgebot_launcher.steam.running_games', return_value=[]), mock.patch('mgebot_launcher.steam.shutil.which', return_value='/usr/bin/steam'), mock.patch('mgebot_launcher.steam.subprocess.Popen') as run:
                launch_training(27025, tf_directory=tf, visibility='friends')
                argv = run.call_args.args[0]
                self.assertNotIn('127.0.0.1', argv)
                self.assertLess(argv.index('mgebot-network'), argv.index('+map'))
                self.assertIn('sv_lan 0', (tf/'cfg/mgebot-network.cfg').read_text())
                self.assertIn('maxplayers 16', (tf/'cfg/mgebot-network.cfg').read_text())

    def test_old_loopback_process_requires_restart_without_killing_it(self):
        with TemporaryDirectory() as tmp:
            tf = Path(tmp); (tf/'cfg').mkdir()
            game = GameProcess(123, '/game/tf_linux64', '-insecure -ip 127.0.0.1', True, tf)
            with mock.patch('mgebot_launcher.steam.subprocess.Popen') as run, self.assertRaisesRegex(RuntimeError, 'Close TF2 once'):
                launch_training(27025, tf_directory=tf, existing=game, visibility='friends')
            run.assert_not_called()


if __name__ == '__main__': unittest.main()
