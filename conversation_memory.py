def _sender_key(message):
    sender = message.get("sender") or {}
    return (
        sender.get("name")
        or sender.get("email")
        or f"message:{message.get('name', 'unknown')}"
    )


def _sender_display_name(message):
    sender = message.get("sender") or {}
    return sender.get("displayName") or sender.get("name") or "Unknown"


def _thread_name(message):
    thread = message.get("thread") or {}
    return thread.get("name")


def quoted_message_metadata(message):
    message_name = message.get("name")
    last_update_time = message.get("lastUpdateTime") or message.get("createTime")
    if not message_name or not last_update_time:
        raise ValueError(
            "Cannot quote a message without its resource name and create/update time."
        )

    return {
        "name": message_name,
        "lastUpdateTime": last_update_time,
    }


def build_quoted_reply_body(text, source_message):
    return {
        "text": text,
        "quotedMessageMetadata": quoted_message_metadata(source_message),
    }


def is_bot_message(message, bot_email, bot_name):
    sender = message.get("sender") or {}
    email = sender.get("email", "").lower()
    display_name = sender.get("displayName", "").lower()
    return (
        email == bot_email.lower()
        or display_name == bot_name.lower()
        or sender.get("name", "").lower() == f"users/{bot_email}".lower()
    )


def is_reply_to_bot(message, history, bot_email, bot_name):
    message_id = message.get("name")
    quoted_metadata = message.get("quotedMessageMetadata") or {}
    quoted_message_id = quoted_metadata.get("name")

    for previous_message in history:
        if previous_message.get("name") == message_id:
            continue
        if quoted_message_id and previous_message.get("name") == quoted_message_id:
            return is_bot_message(previous_message, bot_email, bot_name)

    current_thread = _thread_name(message)
    if not current_thread:
        return False

    return any(
        previous_message.get("name") != message_id
        and _thread_name(previous_message) == current_thread
        and is_bot_message(previous_message, bot_email, bot_name)
        for previous_message in history
    )


def format_conversation_context(messages, current_message, limit=20):
    current_message_id = current_message.get("name")
    history = [
        message
        for message in messages
        if message.get("name") != current_message_id
        and isinstance(message.get("text"), str)
        and message["text"].strip()
    ]
    history = history[-limit:] if limit > 0 else []

    current_thread = _thread_name(current_message)
    thread_history = [
        message for message in history if _thread_name(message) == current_thread
    ]
    explicit_thread_match = bool(current_thread and thread_history)
    if explicit_thread_match:
        history = thread_history

    quoted_metadata = current_message.get("quotedMessageMetadata") or {}
    quoted_message_id = quoted_metadata.get("name")
    quoted_message_found = any(
        message.get("name") == quoted_message_id for message in history
    )

    participant_labels = {}

    def participant_label(message):
        key = _sender_key(message)
        if key not in participant_labels:
            participant_number = len(participant_labels) + 1
            participant_labels[key] = (
                f"Person {participant_number} ({_sender_display_name(message)})"
            )
        return participant_labels[key]

    lines = []
    for message in history:
        marker = " [reply target]" if message.get("name") == quoted_message_id else ""
        timestamp = message.get("createTime")
        time_label = f"[{timestamp}] " if timestamp else ""
        lines.append(f"{time_label}{participant_label(message)}{marker}: {message['text'].strip()}")

    current_sender = participant_label(current_message)
    if explicit_thread_match:
        context_type = "These messages are from the same explicit Google Chat thread."
    elif quoted_message_found:
        context_type = "The current message quotes one of these messages."
    else:
        context_type = (
            "These are recent group chat messages. Infer whether the current message "
            "continues a prior exchange from its wording and conversational flow, even "
            "when it has no explicit reply metadata. Follow the most relevant exchange "
            "when the connection is clear; otherwise answer the current message directly."
        )

    context = "\n".join(lines)
    return (
        f"{context_type}\n"
        "Participant labels identify distinct Google Chat accounts; identical display "
        "names do not necessarily mean the same person.\n"
        f"{context}",
        current_sender,
    )
