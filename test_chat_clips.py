import unittest

from chat_clips import (
    MAX_CLIP_MESSAGE_BYTES,
    get_clip_count,
    has_clip_content,
    image_attachments,
    image_download_url,
    split_clip_text,
)


class ChatClipTests(unittest.TestCase):
    def test_clip_count_remains_limited_without_force(self):
        self.assertEqual(get_clip_count({"text": "Sonny clip 1000"}), 25)

    def test_force_clip_count_ignores_the_default_limit(self):
        self.assertEqual(
            get_clip_count({"text": "Sonny clip 1000 --force"}),
            1000,
        )

    def test_force_flag_requires_a_separate_argument(self):
        self.assertEqual(
            get_clip_count({"text": "Sonny clip 1000 --forced"}),
            25,
        )

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

    def test_chat_uploaded_image_uses_chat_media_download(self):
        attachment = {
            "attachmentDataRef": {"resourceName": "upload/photo"},
        }

        self.assertEqual(
            image_download_url(attachment),
            "https://chat.googleapis.com/v1/media/upload/photo?alt=media",
        )

    def test_drive_image_uses_drive_media_download(self):
        attachment = {
            "driveDataRef": {"driveFileId": "file id/with-reserved"},
        }

        self.assertEqual(
            image_download_url(attachment),
            "https://www.googleapis.com/drive/v3/files/"
            "file%20id%2Fwith-reserved?alt=media&supportsAllDrives=true",
        )

    def test_image_without_download_reference_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "neither a Chat media resource"):
            image_download_url({"contentType": "image/png"})

    def test_drive_image_attachment_is_clippable(self):
        message = {
            "attachments": [
                {
                    "contentName": "upload.jpg",
                    "contentType": "image/jpeg",
                    "attachmentDataRef": {"resourceName": "upload/image"},
                },
                {
                    "contentName": "photo.webp",
                    "contentType": "image/webp",
                    "driveDataRef": {"driveFileId": "drive-image"},
                }
            ]
        }

        self.assertTrue(has_clip_content(message))
        self.assertEqual(len(image_attachments(message)), 2)

    def test_gif_attachment_is_clippable(self):
        message = {
            "attachments": [
                {
                    "contentName": "reaction.gif",
                    "contentType": "image/gif",
                    "attachmentDataRef": {"resourceName": "upload/reaction"},
                }
            ]
        }

        self.assertTrue(has_clip_content(message))
        self.assertEqual(image_attachments(message), message["attachments"])

    def test_large_clip_text_splits_without_loss_or_invalid_utf8(self):
        text = "🙂" * 300_000 + "a" * 1_000_000

        chunks = split_clip_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(
            all(
                len(chunk.encode("utf-8")) <= MAX_CLIP_MESSAGE_BYTES
                for chunk in chunks
            )
        )

    def test_clip_text_prefers_paragraph_boundaries(self):
        chunks = split_clip_text("a" * 12 + "\n\n" + "b" * 12, max_bytes=16)

        self.assertEqual(chunks, ["a" * 12 + "\n\n", "b" * 12])

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
