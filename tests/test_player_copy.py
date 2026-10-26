import unittest
from mgebot_launcher.i18n import error_text, text
from mgebot_launcher.presets import PracticeSettings


class PlayerCopyCase(unittest.TestCase):
    def test_name_errors_keep_validation_without_byte_counts(self):
        for name in ('汉' * 12, 'bad;quit'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as caught:
                    PracticeSettings.parse({'bot_name': name})
                for language in ('ru', 'en'):
                    message = error_text(str(caught.exception), language)
                    self.assertNotRegex(message.casefold(), r'utf|byte|байт|31|32')
                    self.assertNotEqual(message, text('error_retry', language))

    def test_game_close_instruction_survives_shorter_errors(self):
        error = 'Close TF2 and local TF2 servers before installing; live plugin replacement is disabled'
        self.assertIn('TF2', error_text(error, 'ru'))
        self.assertIn('Close', error_text(error, 'en').capitalize())
        self.assertNotIn('plugin', error_text(error, 'en'))

    def test_diagnostics_are_hidden_and_existing_player_messages_are_kept(self):
        for language in ('ru', 'en'):
            self.assertNotIn('schema', error_text('Unknown schema=17 field offset=3', language))
            self.assertNotIn('RCON', error_text('RCON protocol timeout', language))
            message = text('select_game', language)
            self.assertEqual(error_text(message, language), message)
            self.assertEqual(error_text('Error: ' + message, language), message)


if __name__ == '__main__':
    unittest.main()
