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
        w.controls["speed"].setValue(1.35)
        w.controls["jump_rate"].setValue(0.8)
        before = w.settings()
        w.language_box.setCurrentIndex(1)
        w.language_box.setCurrentIndex(0)
        self.assertEqual(w.settings(), before)
        self.assertEqual(w.arena_box.currentData(), 7)
        self.assertEqual(w.settings_tabs.currentIndex(), 1)
        self.assertTrue(w.dirty)
        self.assertEqual(w.language_box.accessibleName(), "interface language")

    def test_exact_dpm_and_numbers_accessible_with_keyboard(self):
        w = self.window
        w._select_page(1)
        w.settings_tabs.setCurrentIndex(1)
        speed = w.controls["speed"]
        speed.spin.setFocus()
        QTest.keyClick(speed.spin, Qt.Key.Key_Up)
        self.assertAlmostEqual(speed.value(), 1.05)
        QTest.keyClick(speed.spin, Qt.Key.Key_Down)
        self.assertAlmostEqual(speed.value(), 1.0)
        row = {"steamid": "synthetic", "name": "Player", "started": 1791513600,
               "status": "completed", "arena": "Spire", "player_score": 20,
               "bot_score": 13, "active_seconds": 231, "damage_out": 1987, "damage_in": 1400}
        w.show_history([row])
        w._select_page(2)
        w.history_table.setCurrentCell(0, 0)
        w.history_table.setFocus()
        for _ in range(5):
            QTest.keyClick(w.history_table, Qt.Key.Key_Right)
        self.assertEqual(w.history_table.currentColumn(), 5)
        self.assertEqual(w.history_table.currentItem().text(), f'{1987 * 60 / 231:.1f}')
        for widget in (w.package_edit, w.language_box, w.arena_box, w.history_player):
            self.assertTrue(widget.accessibleName())


if __name__ == "__main__":
    unittest.main()
