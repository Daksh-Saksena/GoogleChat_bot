import unittest
from unittest.mock import MagicMock

from chat_clips import (
    MAX_CLIP_MESSAGE_BYTES,
    build_clip_post_bodies,
    get_clip_count,
    get_replied_clip_message,
    has_clip_content,
    image_attachments,
    image_download_url,
    is_single_message_clip_request,
    is_clip_request,
    select_previous_clip_messages,
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
        self.assertEqual(
            get_clip_count({"text": "Sonny clip that --force 1000"}),
            1000,
        )

    def test_poller_recognizes_clip_force_before_or_after_count(self):
        for text in ("Sonny clip 20", "Sonny clip --force 20", "Sonny clip 20 --force"):
            with self.subTest(text=text):
                self.assertTrue(is_clip_request({"text": text}))

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

    def test_clip_this_uses_thread_root_when_quote_metadata_is_missing(self):
        root_message = {
            "name": "spaces/test/messages/root",
            "text": "message from ten messages ago",
        }
        trigger_message = {
            "name": "spaces/test/messages/clip-command",
            "text": "Sonny clip this",
            "thread": {"name": "spaces/test/threads/root"},
        }
        service = MagicMock()
        service.spaces().messages().list().execute.return_value = {
            "messages": [
                root_message,
                {
                    "name": trigger_message["name"],
                    "text": trigger_message["text"],
                },
            ]
        }

        self.assertIs(
            get_replied_clip_message(trigger_message, service),
            root_message,
        )
        service.spaces().messages().list.assert_called_with(
            parent="spaces/test",
            filter="thread.name = spaces/test/threads/root",
            pageSize=1000,
            orderBy="createTime asc",
        )

    def test_clip_this_without_a_reply_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Reply directly to it"):
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

    def test_clip_count_keeps_sonny_authored_messages_and_skips_trigger(self):
        trigger = {
            "name": "spaces/test/messages/clip-command",
            "createTime": "2026-11-10T10:00:00Z",
        }
        earlier_messages = [
            {
                "name": f"spaces/test/messages/earlier-{index}",
                "createTime": f"2026-11-10T09:{59 - index:02}:00Z",
                "text": f"Earlier message {index}",
            }
            for index in range(25)
        ]
        sonny_message = earlier_messages[4]
        sonny_message["sender"] = {"email": "sonny@example.com"}
        selected = select_previous_clip_messages(
            [
                trigger,
                {
                    "name": "spaces/test/messages/newer",
                    "createTime": "2026-11-10T10:01:00Z",
                    "text": "Newer message",
                },
                *earlier_messages,
            ],
            20,
            trigger,
        )

        self.assertEqual(len(selected), 20)
        self.assertNotIn(trigger, selected)
        self.assertNotIn("spaces/test/messages/newer", [item["name"] for item in selected])
        self.assertIn(sonny_message, selected)

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

    def test_post_bodies_preserve_all_uploaded_gifs_across_parts(self):
        uploaded_gifs = [
            {"attachmentDataRef": {"attachmentUploadToken": f"gif-{index}"}}
            for index in range(25)
        ]

        bodies = build_clip_post_bodies("Clip of GIFs", uploaded_gifs)

        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[0]["attachment"], uploaded_gifs[:20])
        self.assertEqual(bodies[1]["attachment"], uploaded_gifs[20:])
        self.assertEqual(
            sum(len(body.get("attachment", [])) for body in bodies),
            len(uploaded_gifs),
        )

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
