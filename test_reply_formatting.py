import json
import unittest

from reply_formatting import (
    MAX_REPLY_MESSAGES,
    MAX_REPLY_WORDS,
    REPLY_OUTPUT_FORMAT,
    parse_reply_messages,
)


class ReplyFormattingTests(unittest.TestCase):
    def test_parses_a_single_short_message(self):
        self.assertEqual(
            parse_reply_messages(json.dumps({"messages": ["yeah fair"]})),
            ["yeah fair"],
        )

    def test_parses_multiple_messages_for_separate_chat_bubbles(self):
        self.assertEqual(
            parse_reply_messages(
                json.dumps({"messages": ["first thought", "also this"]})
            ),
            ["first thought", "also this"],
        )

    def test_rejects_replies_over_the_word_limit(self):
        too_many_words = " ".join(["word"] * (MAX_REPLY_WORDS + 1))

        with self.assertRaisesRegex(ValueError, "word limit"):
            parse_reply_messages(json.dumps({"messages": [too_many_words]}))

    def test_rejects_too_many_messages(self):
        messages = ["reply"] * (MAX_REPLY_MESSAGES + 1)

        with self.assertRaisesRegex(ValueError, "1 to"):
            parse_reply_messages(json.dumps({"messages": messages}))

    def test_rejects_empty_messages(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            parse_reply_messages(json.dumps({"messages": [""]}))

    def test_output_schema_requires_array_of_strings(self):
        schema = REPLY_OUTPUT_FORMAT["format"]["schema"]

        self.assertEqual(schema["properties"]["messages"]["type"], "array")
        self.assertEqual(schema["properties"]["messages"]["items"]["type"], "string")
        self.assertFalse(schema["additionalProperties"])

    def test_accepts_exactly_the_word_limit(self):
        reply = " ".join(["word"] * MAX_REPLY_WORDS)

        self.assertEqual(parse_reply_messages(json.dumps({"messages": [reply]})), [reply])


if __name__ == "__main__":
    unittest.main()
