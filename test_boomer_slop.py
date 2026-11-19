import unittest
from unittest.mock import MagicMock

from boomer_slop import (
    BOOMER_FALLBACK_TEMPLATES,
    generate_boomer_slop_post,
    is_boomer_slop_request,
)


class BoomerSlopTests(unittest.TestCase):
    def test_is_boomer_slop_request_detection(self):
        self.assertTrue(is_boomer_slop_request({"text": "sonny facebook quote"}))
        self.assertTrue(is_boomer_slop_request({"text": "Sonny boomer quote please"}))
        self.assertTrue(is_boomer_slop_request({"text": "@Tarkin Gupta boomer slop"}))
        self.assertTrue(is_boomer_slop_request({"text": "Sonny shitpost"}))
        self.assertTrue(is_boomer_slop_request({"text": "give me an inspirational quote"}))
        self.assertTrue(is_boomer_slop_request({"text": "ai slop time"}))
        self.assertFalse(is_boomer_slop_request({"text": "hello how are you"}))
        self.assertFalse(is_boomer_slop_request({"text": "summarize the chat"}))

    def test_generate_boomer_slop_post_fallback(self):
        post = generate_boomer_slop_post(client=None, search_gif_fn=None)
        self.assertIn("https://tenor.com", post)
        self.assertTrue(any(template[0] in post for template in BOOMER_FALLBACK_TEMPLATES))

    def test_generate_boomer_slop_post_with_mock_client_and_gif(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "☕ TEST BOOMER QUOTE AMEN 🙏"
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        mock_search_gif = MagicMock(return_value="https://tenor.com/view/test-minion-gif")

        post = generate_boomer_slop_post(
            client=mock_client,
            model="gpt-4o-mini",
            search_gif_fn=mock_search_gif,
        )

        self.assertIn("☕ TEST BOOMER QUOTE AMEN 🙏", post)
        self.assertIn("https://tenor.com/view/test-minion-gif", post)
        mock_client.chat.completions.create.assert_called_once()
        mock_search_gif.assert_called_once()


if __name__ == "__main__":
    unittest.main()
