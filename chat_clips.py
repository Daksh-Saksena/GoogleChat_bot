def image_attachments(message):
    return [
        attachment
        for attachment in message.get("attachments", [])
        if (attachment.get("contentType") or "").lower().startswith("image/")
    ]


def has_clip_content(message):
    return bool((message.get("text") or "").strip() or image_attachments(message))
