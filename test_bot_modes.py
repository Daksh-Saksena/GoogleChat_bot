import unittest

from bot_modes import (
    SAM_ALTMAN_ACTIVATION_TEXT,
    is_sam_altman_mode_command,
    mentions_ram,
)


class BotModeTests(unittest.TestCase):
    def test_activation_reply_is_exact(self):
        self.assertEqual(SAM_ALTMAN_ACTIVATION_TEXT, "GIMME THE RAM")

    def test_sonny_ram_activates_mode_case_insensitively(self):
        self.assertTrue(is_sam_altman_mode_command("Sonny Ram"))
        self.assertTrue(is_sam_altman_mode_command("@sonny ram please"))

    def test_sonny_ram_requires_both_words_in_order(self):
        self.assertFalse(is_sam_altman_mode_command("Sonny, are you there?"))
        self.assertFalse(is_sam_altman_mode_command("Ram mentioned Sonny"))

    def test_ram_is_matched_as_a_whole_word(self):
        self.assertTrue(mentions_ram("what did Ram say?"))
        self.assertFalse(mentions_ram("programming is fun"))


if __name__ == "__main__":
    unittest.main()
