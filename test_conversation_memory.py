import unittest

from conversation_memory import (
    build_quoted_reply_body,
    format_conversation_context,
    is_reply_to_bot,
    quoted_message_metadata,
)


class ConversationMemoryTests(unittest.TestCase):
    def test_quote_metadata_uses_message_name_and_create_time(self):
        message = {
            "name": "spaces/space/messages/123",
            "createTime": "2026-11-02T10:00:00Z",
        }

        self.assertEqual(
            quoted_message_metadata(message),
            {
                "name": "spaces/space/messages/123",
                "lastUpdateTime": "2026-11-02T10:00:00Z",
            },
        )

    def test_quote_metadata_uses_latest_edit_time(self):
        message = {
            "name": "spaces/space/messages/123",
            "createTime": "2026-11-02T10:00:00Z",
            "lastUpdateTime": "2026-11-02T10:05:00Z",
        }

        self.assertEqual(
            quoted_message_metadata(message)["lastUpdateTime"],
            "2026-11-02T10:05:00Z",
        )

    def test_quote_metadata_requires_message_name_and_timestamp(self):
        with self.assertRaises(ValueError):
            quoted_message_metadata({"name": "spaces/space/messages/123"})

    def test_reply_body_quotes_source_without_creating_a_thread(self):
        body = build_quoted_reply_body(
            "ok sonny",
            {
                "name": "spaces/space/messages/123",
                "createTime": "2026-11-02T10:00:00Z",
            },
        )

        self.assertEqual(
            body,
            {
                "text": "ok sonny",
                "quotedMessageMetadata": {
                    "name": "spaces/space/messages/123",
                    "lastUpdateTime": "2026-11-02T10:00:00Z",
                },
            },
        )
        self.assertNotIn("thread", body)

    def test_detects_reply_in_bot_message_thread_without_trigger_word(self):
        bot_message = {
            "name": "spaces/space/messages/bot",
            "sender": {
                "name": "users/bot@example.com",
                "email": "bot@example.com",
                "displayName": "Tarkin Gupta",
            },
            "thread": {"name": "spaces/space/threads/bot"},
        }
        user_reply = {
            "name": "spaces/space/messages/reply",
            "sender": {"name": "users/1", "displayName": "Alex"},
            "thread": {"name": "spaces/space/threads/bot"},
            "text": "yeah, exactly",
        }

        self.assertTrue(
            is_reply_to_bot(user_reply, [bot_message], "bot@example.com", "Tarkin Gupta")
        )

    def test_detects_quote_reply_to_bot_without_thread_metadata(self):
        bot_message = {
            "name": "spaces/space/messages/bot",
            "sender": {"email": "bot@example.com", "displayName": "Tarkin Gupta"},
        }
        user_reply = {
            "name": "spaces/space/messages/reply",
            "sender": {"name": "users/1", "displayName": "Alex"},
            "quotedMessageMetadata": {"name": "spaces/space/messages/bot"},
            "text": "what did you mean?",
        }

        self.assertTrue(
            is_reply_to_bot(user_reply, [bot_message], "bot@example.com", "Tarkin Gupta")
        )

    def test_does_not_trigger_for_reply_to_another_user(self):
        other_message = {
            "name": "spaces/space/messages/other",
            "sender": {"name": "users/2", "displayName": "Sam"},
            "thread": {"name": "spaces/space/threads/other"},
        }
        user_reply = {
            "name": "spaces/space/messages/reply",
            "sender": {"name": "users/1", "displayName": "Alex"},
            "thread": {"name": "spaces/space/threads/other"},
            "text": "yeah, exactly",
        }

        self.assertFalse(
            is_reply_to_bot(user_reply, [other_message], "bot@example.com", "Tarkin Gupta")
        )

    def test_distinguishes_people_with_the_same_display_name(self):
        messages = [
            {
                "name": "spaces/space/messages/1",
                "sender": {"name": "users/1", "displayName": "Alex"},
                "text": "first person",
            },
            {
                "name": "spaces/space/messages/2",
                "sender": {"name": "users/2", "displayName": "Alex"},
                "text": "second person",
            },
        ]
        current_message = {
            "name": "spaces/space/messages/3",
            "sender": {"name": "users/1", "displayName": "Alex"},
        }

        context, current_sender = format_conversation_context(messages, current_message)

        self.assertIn("Person 1 (Alex): first person", context)
        self.assertIn("Person 2 (Alex): second person", context)
        self.assertEqual(current_sender, "Person 1 (Alex)")

    def test_prefers_history_from_the_explicit_thread(self):
        messages = [
            {
                "name": "spaces/space/messages/1",
                "sender": {"name": "users/1", "displayName": "Alex"},
                "thread": {"name": "spaces/space/threads/one"},
                "text": "same thread",
            },
            {
                "name": "spaces/space/messages/2",
                "sender": {"name": "users/2", "displayName": "Sam"},
                "thread": {"name": "spaces/space/threads/two"},
                "text": "unrelated thread",
            },
        ]
        current_message = {
            "name": "spaces/space/messages/3",
            "sender": {"name": "users/2", "displayName": "Sam"},
            "thread": {"name": "spaces/space/threads/one"},
        }

        context, _ = format_conversation_context(messages, current_message)

        self.assertIn("same explicit Google Chat thread", context)
        self.assertIn("same thread", context)
        self.assertNotIn("unrelated thread", context)

    def test_marks_an_explicitly_quoted_message(self):
        messages = [
            {
                "name": "spaces/space/messages/1",
                "sender": {"name": "users/1", "displayName": "Alex"},
                "text": "quoted text",
            }
        ]
        current_message = {
            "name": "spaces/space/messages/2",
            "sender": {"name": "users/2", "displayName": "Sam"},
            "quotedMessageMetadata": {"name": "spaces/space/messages/1"},
        }

        context, _ = format_conversation_context(messages, current_message)

        self.assertIn("current message quotes", context)
        self.assertIn("[reply target]", context)

    def test_limits_history_to_the_most_recent_messages(self):
        messages = [
            {
                "name": f"spaces/space/messages/{i}",
                "sender": {"name": "users/1", "displayName": "Alex"},
                "text": f"message {i}",
            }
            for i in range(25)
        ]
        current_message = {
            "name": "spaces/space/messages/current",
            "sender": {"name": "users/2", "displayName": "Sam"},
        }

        context, _ = format_conversation_context(messages, current_message, limit=20)

        self.assertNotIn("message 4\n", context)
        self.assertIn("message 5", context)
        self.assertIn("message 24", context)

    def test_excludes_the_current_message_from_history(self):
        current_message = {
            "name": "spaces/space/messages/current",
            "sender": {"name": "users/1", "displayName": "Alex"},
            "text": "latest message",
        }

        context, _ = format_conversation_context([current_message], current_message)

        self.assertNotIn("latest message", context)


if __name__ == "__main__":
    unittest.main()
