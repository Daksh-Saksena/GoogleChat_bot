import unittest

from chat_clips import has_clip_content, image_attachments


class ChatClipTests(unittest.TestCase):
    def test_image_only_message_can_be_clipped(self):
        message = {
            "attachments": [
                {
                    "contentName": "photo.png",
                    "contentType": "image/png",
                    "attachmentDataRef": {"resourceName": "upload/photo"},
                }
            ]
        }

        self.assertTrue(has_clip_content(message))
        self.assertEqual(len(image_attachments(message)), 1)

    def test_non_image_attachment_does_not_make_message_clippable(self):
        message = {
            "attachments": [{"contentType": "application/pdf"}],
        }

        self.assertFalse(has_clip_content(message))
        self.assertEqual(image_attachments(message), [])

    def test_text_messages_remain_clippable(self):
        self.assertTrue(has_clip_content({"text": "hello"}))
        self.assertFalse(has_clip_content({"text": "  "}))


if __name__ == "__main__":
    unittest.main()
