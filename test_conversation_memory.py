import unittest

from conversation_memory import format_conversation_context


class ConversationMemoryTests(unittest.TestCase):
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
