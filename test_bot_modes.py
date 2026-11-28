import unittest

from bot_modes import (
    SAM_ALTMAN_ACTIVATION_TEXT,
    SAM_ALTMAN_DEACTIVATION_TEXT,
    DAKSH_REPLY_TEXT,
    is_daksh_reply_user,
    is_sam_altman_deactivation_command,
    is_sam_altman_mode_command,
    mentions_ram,
)


class BotModeTests(unittest.TestCase):
    def test_activation_reply_is_exact(self):
        self.assertEqual(SAM_ALTMAN_ACTIVATION_TEXT, "GIMME THE RAM")
        self.assertEqual(SAM_ALTMAN_DEACTIVATION_TEXT, "ram altman disabled")

    def test_daksh_reply_matches_sender_email_case_insensitively(self):
        self.assertTrue(
            is_daksh_reply_user({"email": "DakshSaksena2011@gmail.com"})
        )
        self.assertFalse(is_daksh_reply_user({"email": "someone@example.com"}))
        self.assertFalse(is_daksh_reply_user({"name": "users/123"}))
        self.assertEqual(DAKSH_REPLY_TEXT, "meet me after 3 over there")

    def test_sonny_ram_activates_mode_case_insensitively(self):
        self.assertTrue(is_sam_altman_mode_command("Sonny Ram"))
        self.assertTrue(is_sam_altman_mode_command("@sonny ram please"))

    def test_sonny_ram_requires_both_words_in_order(self):
        self.assertFalse(is_sam_altman_mode_command("Sonny, are you there?"))
        self.assertFalse(is_sam_altman_mode_command("Ram mentioned Sonny"))
        self.assertFalse(is_sam_altman_mode_command("Sonny no ram"))

    def test_sonny_no_ram_is_a_distinct_deactivation_command(self):
        self.assertTrue(is_sam_altman_deactivation_command("Sonny no ram"))
        self.assertTrue(is_sam_altman_deactivation_command("@SONNY NO RAM"))
        self.assertFalse(is_sam_altman_deactivation_command("Sonny ram"))
        self.assertFalse(is_sam_altman_deactivation_command("Sonny, no rambling"))

    def test_ram_is_matched_as_a_whole_word(self):
        self.assertTrue(mentions_ram("what did Ram say?"))
        self.assertFalse(mentions_ram("programming is fun"))

    def test_trumpglazer_mode_validation(self):
        from summarize_chat import is_switch_to_trump
        self.assertTrue(is_switch_to_trump({"text": "Sonny trumpglazer"}))
        self.assertTrue(is_switch_to_trump({"text": "trump glazer"}))
        self.assertTrue(is_switch_to_trump({"text": "@sonny trump"}))
        self.assertFalse(is_switch_to_trump({"text": "hello how are you"}))


if __name__ == "__main__":
    unittest.main()
