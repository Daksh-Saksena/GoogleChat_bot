import unittest
from unittest.mock import MagicMock

from chat_clips import (
    MAX_CLIP_MESSAGE_BYTES,
    get_clip_count,
    get_replied_clip_message,
    has_clip_content,
    image_attachments,
    image_download_url,
    is_single_message_clip_request,
    split_clip_text,
)


class ChatClipTests(unittest.TestCase):
    def test_explicit_clip_count_is_not_capped(self):
        self.assertEqual(get_clip_count({"text": "Sonny clip 1000"}), 1000)

    def test_force_flag_remains_compatible(self):
        self.assertEqual(
            get_clip_count({"text": "Sonny clip 1000 --force"}),
            1000,
        )
        self.assertEqual(
            get_clip_count({"text": "Sonny clip --force 1000"}),
            1000,
        )

    def test_clip_this_is_a_single_message_request(self):
        self.assertTrue(
            is_single_message_clip_request({"text": "Sonny clip this"})
        )
        self.assertTrue(
            is_single_message_clip_request({"text": "@Sonny, CLIP THIS please"})
        )
        self.assertFalse(
            is_single_message_clip_request({"text": "Sonny clip that"})
        )
        self.assertFalse(
            is_single_message_clip_request({"text": "Sonny clip 5"})
        )

    def test_replied_gif_message_is_fetched_as_single_clip_target(self):
        target_message = {
            "text": "look at this",
            "attachment": [
                {
                    "contentName": "reaction.gif",
                    "contentType": "image/gif",
                    "attachmentDataRef": {"resourceName": "upload/reaction"},
                }
            ],
        }
        service = MagicMock()
        service.spaces().messages().get().execute.return_value = target_message
        trigger_message = {
            "quotedMessageMetadata": {"name": "spaces/test/messages/target"},
        }

        self.assertIs(
            get_replied_clip_message(trigger_message, service),
            target_message,
        )
        service.spaces().messages().get.assert_any_call(
            name="spaces/test/messages/target"
        )

    def test_clip_this_without_a_reply_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Reply to the message"):
            get_replied_clip_message({"text": "Sonny clip this"}, MagicMock())

    def test_replied_message_without_clip_content_is_rejected(self):
        service = MagicMock()
        service.spaces().messages().get().execute.return_value = {
            "attachments": [{"contentType": "application/pdf"}],
        }

        with self.assertRaisesRegex(ValueError, "no text or supported images"):
            get_replied_clip_message(
                {"quotedMessageMetadata": {"name": "spaces/test/messages/target"}},
                service,
            )

    def test_unrecognized_force_variant_does_not_change_requested_count(self):
        self.assertEqual(
            get_clip_count({"text": "Sonny clip 1000 --forced"}),
            1000,
        )

    def test_image_only_message_can_be_clipped(self):
        message = {
            "attachment": [
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
            "attachment": [
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

    def test_image_attachment_is_recognized_from_filename_when_mime_is_missing(self):
        image = {
            "contentName": "photo.png",
            "attachmentDataRef": {"resourceName": "upload/photo"},
        }
        message = {"attachment": [image]}

        self.assertTrue(has_clip_content(message))
        self.assertEqual(image_attachments(message), [image])

    def test_single_attachment_object_is_supported(self):
        image = {"contentName": "reaction.gif", "contentType": "image/gif"}

        self.assertEqual(image_attachments({"attachment": image}), [image])

    def test_singular_api_field_takes_precedence_over_legacy_plural_alias(self):
        uploaded_image = {"contentType": "image/png", "contentName": "uploaded.png"}
        legacy_image = {"contentType": "image/gif", "contentName": "legacy.gif"}
        message = {
            "attachment": [uploaded_image],
            "attachments": [legacy_image],
        }

        self.assertEqual(image_attachments(message), [uploaded_image])

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
