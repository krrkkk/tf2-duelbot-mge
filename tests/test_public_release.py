from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton

from mgebot_launcher.gui import MainWindow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package


class PublicInterfaceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_player_controls_and_preferences_without_operator_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            window = MainWindow(Path(temporary), demo=True)
            window.show()
            try:
                self.assertIsNone(importlib.util.find_spec("mgebot_launcher.review"))
                self.assertFalse(hasattr(window, "review"))
                for language in ("en", "ru"):
                    window.language_box.setCurrentIndex(window.language_box.findData(language))
                    self.app.processEvents()
                    self.assertEqual(window.language, language)
                    self.assertEqual({s.key().toString() for s in window.findChildren(QShortcut)},
                                     {"Ctrl+1", "Ctrl+2", "Ctrl+S", "Ctrl+Return"})
                    QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
                    self.app.processEvents()
                    self.assertFalse(any(d.isVisible() for d in window.findChildren(QDialog)))
                    self.assertEqual(window.pages.count(), 2)
                    buttons = []
                    def inspect(dialog):
                        buttons.extend(b.text() for b in dialog.findChildren(QPushButton))
                        return QDialog.DialogCode.Rejected
                    with patch.object(QDialog, "exec", inspect):
                        window._preferences()
                    for key in ("browse", "crash_logs", "repair", "save"):
                        self.assertIn(window.t(key), buttons)
                    self.assertFalse(any(value in text for text in buttons for value in
                                         ("Operator", "Feedback", "оператор", "Правк")))
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()


class PublicExportCase(unittest.TestCase):
    def test_current_source_export_has_no_private_entries(self):
        paths = package.source_files()
        self.assertTrue(paths)
        self.assertFalse(any(p.name == "review.py" for p in paths))
        self.assertTrue(any(p.name == "gui.py" for p in paths))

    def test_export_refuses_operator_module_and_local_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "mgebot_launcher"
            folder.mkdir()
            with patch.object(package, "ROOT", root):
                for name in ("review.py", "connection.json", "errors.log", "crash.dmp", ".env"):
                    with self.subTest(name=name):
                        path = folder / name
                        path.write_text("fixture")
                        with self.assertRaises(ValueError):
                            package.source_files()
                        path.unlink()


if __name__ == "__main__":
    unittest.main()
