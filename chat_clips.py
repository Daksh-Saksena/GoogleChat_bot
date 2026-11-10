import re
import urllib.parse


MAX_CLIP_MESSAGE_BYTES = 24_000


def is_single_message_clip_request(message):
    return bool(re.search(r"\bclip\s+this\b", message.get("text", ""), re.IGNORECASE))


def get_replied_clip_message(trigger_message, service):
    quoted_message_name = (
        trigger_message.get("quotedMessageMetadata") or {}
    ).get("name")
    if not quoted_message_name:
        raise ValueError(
            "Reply to the message you want clipped, then say 'Sonny clip this'."
        )

    message = service.spaces().messages().get(
        name=quoted_message_name
    ).execute(num_retries=5)
    if not has_clip_content(message):
        raise ValueError("The message you replied to has no text or supported images.")
    return message


def image_attachments(message):
    return [
        attachment
        for attachment in message.get("attachments", [])
        if (attachment.get("contentType") or "").lower().startswith("image/")
    ]


def image_download_url(attachment):
    data_ref = attachment.get("attachmentDataRef") or {}
    resource_name = data_ref.get("resourceName")
    if resource_name:
        return (
            "https://chat.googleapis.com/v1/media/"
            f"{urllib.parse.quote(resource_name, safe='/')}?alt=media"
        )

    drive_ref = attachment.get("driveDataRef") or {}
    drive_file_id = drive_ref.get("driveFileId")
    if drive_file_id:
        return (
            "https://www.googleapis.com/drive/v3/files/"
            f"{urllib.parse.quote(drive_file_id, safe='')}?"
            "alt=media&supportsAllDrives=true"
        )

    raise ValueError(
        "The image attachment has neither a Chat media resource nor a Drive file ID."
    )


def split_clip_text(text, max_bytes=MAX_CLIP_MESSAGE_BYTES):
    if max_bytes < 4:
        raise ValueError("max_bytes must be at least 4 to preserve UTF-8 characters.")

    encoded = text.encode("utf-8")
    chunks = []
    start = 0

    while start < len(encoded):
        end = min(start + max_bytes, len(encoded))
        if end < len(encoded):
            boundary = end
            while boundary > start and encoded[boundary] & 0xC0 == 0x80:
                boundary -= 1

            separator = encoded.rfind(b"\n\n", start + max_bytes // 2, boundary)
            end = separator + 2 if separator >= 0 else boundary

        if end <= start:
            raise ValueError("Unable to split clip text within the byte limit.")

        chunks.append(encoded[start:end].decode("utf-8"))
        start = end

    return chunks or [""]


def get_clip_count(message):
    text = message.get("text", "")
    match = re.search(r"clip(?:\s+that)?\s+(\d+)", text, re.IGNORECASE)
    if not match:
        return 1

    try:
        count = max(1, int(match.group(1)))
    except ValueError:
        return 1

    return count


def has_clip_content(message):
    return bool((message.get("text") or "").strip() or image_attachments(message))
