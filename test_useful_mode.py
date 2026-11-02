import json
import unittest
from types import SimpleNamespace

from useful_mode import (
    MAX_SEARCH_MESSAGES,
    USEFUL_MODE_TOOLS,
    parse_useful_request,
    run_useful_assistant,
    search_chat_messages,
)


class UsefulModeTests(unittest.TestCase):
    def test_detects_prefix_and_returns_request(self):
        self.assertEqual(
            parse_useful_request("Sonny useful, look this up"),
            "look this up",
        )

    def test_detects_prefix_case_insensitively(self):
        self.assertEqual(
            parse_useful_request("@SONNY USEFUL: what did we decide?"),
            "what did we decide?",
        )

    def test_does_not_match_useful_word_in_the_middle(self):
        self.assertIsNone(parse_useful_request("hey Sonny useful look this up"))

    def test_chat_search_ranks_matching_messages_and_keeps_sender_ids(self):
        messages = [
            {
                "name": "spaces/s/messages/1",
                "createTime": "2026-11-02T10:00:00Z",
                "sender": {"name": "users/1", "displayName": "Alex"},
                "text": "We chose the blue design for the website.",
            },
            {
                "name": "spaces/s/messages/2",
                "createTime": "2026-11-02T11:00:00Z",
                "sender": {"name": "users/2", "displayName": "Alex"},
                "text": "The website launch is next week.",
            },
            {
                "name": "spaces/s/messages/3",
                "sender": {"name": "users/3", "displayName": "Sam"},
                "text": "Lunch was nice.",
            },
        ]

        results = search_chat_messages(messages, "website design")

        self.assertEqual(results[0]["sender_id"], "users/1")
        self.assertIn("blue design", results[0]["text"])
        self.assertEqual(len(results), 2)

    def test_search_is_bounded_to_latest_1000_input_messages(self):
        messages = [
            {"text": "needle"} for _ in range(MAX_SEARCH_MESSAGES)
        ] + [{"text": "needle from older history"}]

        results = search_chat_messages(messages, "needle")

        self.assertEqual(len(results), 5)
        self.assertNotIn("older history", str(results))

    def test_tool_list_includes_web_search_and_supported_chat_actions(self):
        tool_names = {
            tool.get("name", tool["type"])
            for tool in USEFUL_MODE_TOOLS
        }

        self.assertIn("web_search", tool_names)
        self.assertIn("search_chat_history", tool_names)
        self.assertIn("post_chat_message", tool_names)
        self.assertIn("create_poll", tool_names)

    def test_runs_function_tools_and_returns_final_answer(self):
        call = SimpleNamespace(
            type="function_call",
            name="search_chat_history",
            arguments='{"query":"website"}',
            call_id="call-1",
        )
        first_response = SimpleNamespace(
            output=[call],
            output_text="",
        )
        final_response = SimpleNamespace(
            output=[SimpleNamespace(type="message")],
            output_text="We chose the blue design.",
        )

        class FakeResponses:
            def __init__(self):
                self.calls = []
                self.responses = [first_response, final_response]

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return self.responses.pop(0)

        fake_client = SimpleNamespace(responses=FakeResponses())
        tool_calls = []

        answer = run_useful_assistant(
            fake_client,
            "test-model",
            "What did we decide?",
            {
                "search_chat_history": lambda arguments: (
                    tool_calls.append(arguments) or [{"text": "blue design"}]
                )
            },
        )

        self.assertEqual(answer, "We chose the blue design.")
        self.assertEqual(tool_calls, [{"query": "website"}])
        tool_outputs = fake_client.responses.calls[1]["input"]
        self.assertEqual(
            json.loads(tool_outputs[-1]["output"]),
            {"ok": True, "result": [{"text": "blue design"}]},
        )


if __name__ == "__main__":
    unittest.main()
