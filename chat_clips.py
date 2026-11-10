import re


MAX_CLIP_COUNT = 25


def image_attachments(message):
    return [
        attachment
        for attachment in message.get("attachments", [])
        if (attachment.get("contentType") or "").lower().startswith("image/")
    ]


def get_clip_count(message):
    text = message.get("text", "")
    match = re.search(r"clip(?:\s+that)?\s+(\d+)", text, re.IGNORECASE)
    if not match:
        return 1

    try:
        count = max(1, int(match.group(1)))
    except ValueError:
        return 1

    force = bool(re.search(r"(?:^|\s)--force(?:\s|$)", text, re.IGNORECASE))
    return count if force else min(count, MAX_CLIP_COUNT)


def has_clip_content(message):
    return bool((message.get("text") or "").strip() or image_attachments(message))
