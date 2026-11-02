import json
import re


MAX_SEARCH_MESSAGES = 1000
MAX_SEARCH_RESULTS = 10
MAX_TOOL_ROUNDS = 5

USEFUL_MODE_TOOLS = [
    {"type": "web_search"},
    {
        "type": "function",
        "name": "search_chat_history",
        "description": (
            "Search the latest 1000 accessible messages in the configured Google Chat "
            "space. Use this when asked what the group said, when something happened, "
            "or who said something."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "post_chat_message",
        "description": (
            "Post a message to the source Google Chat space, quoted as a reply to the "
            "user's request. Use only when the user explicitly asks you to send or post."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "create_poll",
        "description": (
            "Create and post a poll in the source Google Chat space when explicitly "
            "requested. Provide a clear question and 2 to 6 options."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["question", "options"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "clip_recent_messages",
        "description": (
            "Clip the specified number of recent non-bot messages and post them to "
            "the configured highlights space. Use only when explicitly requested."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "summarize_recent_chat",
        "description": (
            "Generate a newspaper-style summary of recent source-space messages and "
            "post it to the configured destination space. Use only when requested."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
]

_STOP_WORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be", "been",
    "before", "but", "by", "did", "do", "for", "from", "he", "her", "him", "his",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "our", "said", "say",
    "she", "so", "that", "the", "their", "them", "they", "this", "to", "us", "was",
    "we", "what", "when", "where", "who", "why", "with", "you", "your",
}


def parse_useful_request(text):
    if not isinstance(text, str):
        return None
    match = re.match(r"^\s*@?sonny\s+useful\b[\s,:-]*", text or "", re.IGNORECASE)
    if not match:
        return None
    return text[match.end():].strip()


def search_chat_messages(messages, query, limit=5):
    if not isinstance(query, str):
        raise ValueError("The chat-history search query must be text.")
    terms = {
        term.lower()
        for term in re.findall(r"[\w'-]+", query)
        if len(term) > 1 and term.lower() not in _STOP_WORDS
    }
    if not terms:
        return []

    matches = []
    for message in messages[:MAX_SEARCH_MESSAGES]:
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            continue

        normalized_text = text.casefold()
        matched_terms = {term for term in terms if term in normalized_text}
        if not matched_terms:
            continue

        score = len(matched_terms)
        if query.strip().casefold() in normalized_text:
            score += len(terms) + 1
        matches.append((score, message))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].get("createTime", ""),
        ),
        reverse=True,
    )

    results = []
    for score, message in matches[:max(1, min(limit, MAX_SEARCH_RESULTS))]:
        sender = message.get("sender") or {}
        results.append(
            {
                "created_at": message.get("createTime"),
                "sender": sender.get("displayName") or "Unknown",
                "sender_id": sender.get("name") or sender.get("email"),
                "text": message["text"][:2000],
                "relevance": score,
            }
        )
    return results


def run_useful_assistant(client, model, request, tool_handlers):
    instructions = (
        "You are Sonny Useful, a capable general assistant for a Google Chat group. "
        "Answer directly and naturally, not in any roleplay persona. Use web_search "
        "for current facts, research, or anything that needs up-to-date web information. "
        "Use search_chat_history for questions about what people said in this group; "
        "only claim historical details supported by its results. You may execute the "
        "provided chat actions immediately when the user explicitly asks for them; do "
        "not take an action merely because it seems helpful. Never claim an action "
        "succeeded unless its tool result confirms success. Mention uncertainty when "
        "search results are incomplete. Keep the final answer useful and appropriately "
        "concise. If an action tool already posted a message or summary, do not repeat "
        "the posted content in your final answer; briefly confirm what happened."
    )
    input_items = [{"role": "user", "content": request}]

    for tool_round in range(MAX_TOOL_ROUNDS + 1):
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=input_items,
            tools=USEFUL_MODE_TOOLS,
        )
        function_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        if not function_calls:
            answer = response.output_text.strip()
            if not answer:
                raise ValueError("The useful assistant returned an empty response.")
            return answer
        if tool_round == MAX_TOOL_ROUNDS:
            raise RuntimeError(
                f"The useful assistant reached its {MAX_TOOL_ROUNDS}-round tool limit."
            )

        input_items.extend(response.output)
        for call in function_calls:
            try:
                arguments = json.loads(call.arguments)
                handler = tool_handlers.get(call.name)
                if handler is None:
                    raise ValueError(f"Unsupported useful-mode action: {call.name}")
                result = handler(arguments)
                tool_output = {"ok": True, "result": result}
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                tool_output = {"ok": False, "error": str(error)}
            except Exception as error:
                print(f"Useful-mode tool {call.name} failed: {error}")
                tool_output = {
                    "ok": False,
                    "error": f"{call.name} failed: {error}",
                }

            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(tool_output),
                }
            )

    raise RuntimeError("The useful assistant exited without a final response.")
