import unittest
from dataclasses import asdict, replace
from mgebot_launcher.presets import PracticeSettings
from mgebot_launcher.loadouts import LOADOUTS


class RetiredSettingsCase(unittest.TestCase):
    def test_legacy_preset_keeps_other_preferences_and_migrates_retired_fields(self):
        old = replace(PracticeSettings(), bot_name='Тренер', bot_chat=2,
                      primary_item=730, secondary_item=415, melee_item=775,
                      mirror_gear=True, respawn_delay=.4, aim_delay=.8)
        migrated = PracticeSettings.parse(asdict(old))
        self.assertEqual(migrated, replace(old, bot_chat=0, primary_item=-1))
        self.assertEqual(PracticeSettings.parse(asdict(migrated)), migrated)

    def test_outbound_legacy_columns_cannot_reenable_removed_features(self):
        text = replace(PracticeSettings(), bot_chat=1, primary_item=730).to_keyvalues()
        self.assertIn('"bot_chat" "0"', text)
        self.assertIn('"primary_item" "-1"', text)
        self.assertNotIn('"730"', text)
        self.assertNotIn(730, [item[0] for item in LOADOUTS])

    def test_legacy_migration_retains_validation_for_bad_input(self):
        for values in ({'bot_chat': '2'}, {'bot_chat': 3}, {'primary_item': True},
                       {'respawn_delay': float('nan')}, {'bot_name': 'bad;quit'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PracticeSettings.parse(values)


if __name__ == '__main__':
    unittest.main()
