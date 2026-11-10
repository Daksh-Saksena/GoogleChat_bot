import json
import re


MAX_REPLY_WORDS = 60
MAX_REPLY_MESSAGES = 3

REPLY_OUTPUT_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "chat_reply",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["messages"],
            "additionalProperties": False,
        },
    }
}


def parse_reply_messages(output_text):
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as error:
        raise ValueError("The generated chat reply was not valid JSON.") from error

    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_REPLY_MESSAGES:
        raise ValueError(
            f"A reply must contain 1 to {MAX_REPLY_MESSAGES} messages."
        )
    if any(not isinstance(message, str) or not message.strip() for message in messages):
        raise ValueError("Each generated chat message must be a non-empty string.")

    cleaned_messages = [message.strip() for message in messages]
    word_count = len(re.findall(r"\b[\w'-]+\b", " ".join(cleaned_messages)))
    if word_count > MAX_REPLY_WORDS:
        raise ValueError(
            f"The generated chat reply exceeded the {MAX_REPLY_WORDS}-word limit "
            f"({word_count} words)."
        )

    return cleaned_messages


def first_reply_message(messages):
    return messages[0] if messages else None
