from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from mgebot_launcher.gui import MainWindow
from mgebot_launcher.presets import BotSettings


class WorkflowCase(unittest.TestCase):
    def test_ai_teammate_only_in_waiting_room_and_pending_request_is_disabled(self):
        w=self.window;w._set_mode('duo');w.set_online(True);events=[]
        w.teammate_requested.connect(lambda:events.append('teammate'))
        room={'active':False,'team':{'hosting':True,'waiting':True}}
        w.show_snapshot(room);self.assertTrue(w.teammate_button.isEnabled())
        w.teammate_button.click();self.assertEqual(events,['teammate'])
        w.set_action_busy(True);self.assertFalse(w.teammate_button.isEnabled());w.set_action_busy(False)
        room['team']['pending_bot']=True;w.show_snapshot(room);self.assertFalse(w.teammate_button.isEnabled())
        room['team'].update(waiting=False,pending_bot=False,teammate_bot=True,partner_name='Bot')
        w.show_snapshot(room);self.assertFalse(w.teammate_button.isVisible());self.assertIn(w.t('bot_teammate'),w.team_label.text())
        w.language_box.setCurrentIndex(1);self.assertIn('бот-напарник',w.team_label.text().casefold())
        w.show_snapshot({});self.assertFalse(w.teammate_button.isEnabled())

    def test_duo_round_status_and_deny_control(self):
        w=self.window;w._set_mode('duo');w.set_online(True)
        self.assertTrue(w.practice_controls['shotgun_deny'].isEnabled())
        w.practice_controls['shotgun_deny'].setChecked(False);self.assertFalse(w.practice_settings().shotgun_deny)
        w.show_snapshot({'active':True,'team':{'hosting':True,'waiting':False,'round':2,'phase':'fighting','alive_team':1,'alive_opponents':2,'player_out':True}})
        self.assertIn('round',w.team_label.text().lower());self.assertIn('1 : 2',w.team_label.text())
        w.language_box.setCurrentIndex(1);self.assertIn('выбиты',w.team_label.text().lower());self.assertFalse(w.practice_settings().shotgun_deny)
        self.assertIn('!add',w.t('invite_note'));self.assertNotIn('!2v2',w.t('invite_note'))

    def test_switchgun_is_editable_and_gunboats_remain_exclusive(self):
        w=self.window;w.set_settings(BotSettings(bot_class=3,switchgun=True))
        self.assertTrue(w.settings().switchgun)
        w.controls['gunboats'].setChecked(True);self.assertTrue(w.settings().gunboats);self.assertFalse(w.settings().switchgun)

    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.temporary.name))
        self.window.set_arenas([{"id": 4, "name": "Spire", "occupied": False},
                                {"id": 7, "name": "Granary", "occupied": False}])
        self.window.arena_box.setCurrentIndex(1)
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        self.temporary.cleanup()

    def test_preset_edits_apply_explicitly_and_new_duel_is_separate(self):
        w = self.window
        events = []
        w.apply_requested.connect(lambda settings: events.append(("apply", settings)))
        w.launch_requested.connect(lambda settings, arena: events.append(("start", arena)))
        preset = w.store.save("Precision", BotSettings.parse({"speed": 1.15}))
        w.load_presets()
        w.preset_box.setCurrentIndex(w.preset_box.findData(preset.id))
        self.assertEqual(events, [])
        self.assertTrue(w.main_button.property("primary"))
        self.assertFalse(w.apply_button.isEnabled())
        self.assertEqual(w.dirty_label.text(), w.t("dirty_offline"))
        w.set_online(True)
        w.show_snapshot({"active": True, "name": "Player", "session": {}})
        self.assertTrue(w.apply_button.property("primary"))
        self.assertFalse(w.new_duel_button.property("primary"))
        self.assertEqual(w.new_duel_button.text(), w.t("new_duel"))
        w.apply_button.click()
        self.assertEqual(events, [("apply", preset.settings)])
        w.set_action_busy(True)
        w.controls["speed"].setValue(1.2)
        self.assertFalse(w.apply_button.isEnabled())
        self.assertFalse(w.new_duel_button.isEnabled())
        w.set_action_busy(False)
        w.new_duel_button.click()
        self.assertEqual(events[-1], ("start", 7))

    def test_language_preserves_draft_arena_and_settings_tab(self):
        w = self.window
        w.settings_tabs.setCurrentIndex(1)
        w.controls["speed"].spin.setValue(1.35)
        w.controls["jump_rate"].spin.setValue(0.8)
        before = w.settings()
        w.language_box.setCurrentIndex(1)
        w.language_box.setCurrentIndex(0)
        self.assertEqual(w.settings(), before)
        self.assertEqual(w.arena_box.currentData(), 7)
        self.assertEqual(w.settings_tabs.currentIndex(), 1)
        self.assertTrue(w.dirty)
        self.assertEqual(w.language_box.accessibleName(), "interface language")

    def test_statistics_removed_and_new_rules_are_editable(self):
        w = self.window
        self.assertEqual(w.pages.count(), 2)
        self.assertFalse(hasattr(w, "history_table"))
        w._select_page(1)
        w._rules_preset("classic50")
        self.assertEqual((w.settings().player_hp, w.settings().bot_hp, w.settings().frag_limit), (300, 300, 50))
        self.assertEqual(w.practice_settings().ammo_policy, 0)
        w.practice_controls["aim_delay"].setValue(.8)
        w.practice_controls["respawn_sound"].setChecked(False)
        before = w.practice_settings()
        w.language_box.setCurrentIndex(1)
        self.assertEqual(w.practice_settings(), before)
        w.practice_controls["random_reaction"].setChecked(True)
        self.assertTrue(w.practice_controls["preset_1_weight"].isEnabled())

    def test_mode_selection_stays_checked_and_connection_refreshes_apply_caption(self):
        w = self.window
        w.mode_buttons["solo"].click()
        self.assertTrue(w.mode_buttons["solo"].isChecked())
        w.mode_buttons["duo"].click(); w.mode_buttons["duo"].click()
        self.assertTrue(w.mode_buttons["duo"].isChecked())
        self.assertFalse(w.mode_buttons["solo"].isChecked())
        w.mark_dirty(True); self.assertEqual(w.dirty_label.text(), w.t("dirty_offline"))
        w.set_online(True); self.assertEqual(w.dirty_label.text(), w.t("dirty"))
        self.assertTrue(w.apply_button.isEnabled())
        w.set_online(False); self.assertEqual(w.dirty_label.text(), w.t("dirty_offline"))

    def test_duo_filters_arenas_and_keeps_single_player_modifiers_separate(self):
        w = self.window
        w.set_arenas([{"id": 1, "name": "Solo", "duo": False}, {"id": 2, "name": "Team", "duo": True}])
        w._set_mode("duo")
        self.assertEqual(w.arena_box.count(), 1)
        self.assertEqual(w.arena_box.currentData(), 2)
        self.assertTrue(w.controls["skill_step"].isEnabled())
        self.assertFalse(w.practice_controls["infinite_player"].isEnabled())
        w.set_online(True)
        w.show_snapshot({"active": False, "team": {"hosting": True, "waiting": True}})
        self.assertFalse(w.main_button.isVisible())
        self.assertTrue(w.stop_button.isEnabled())
        self.assertTrue(w.invite_button.isEnabled())
        self.assertIn(w.t("waiting_partner"), w.team_label.text())
        w.language_box.setCurrentIndex(1)
        self.assertEqual(w.mode, "duo")


if __name__ == "__main__":
    unittest.main()
