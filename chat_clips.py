import mimetypes
import re
import urllib.parse
from datetime import datetime


MAX_CLIP_MESSAGE_BYTES = 24_000


def is_clip_request(message):
    return bool(
        re.search(
            r"\bclip(?:\s+(?:that|this|--force|\d+))*\b",
            message.get("text", ""),
            re.IGNORECASE,
        )
    )


def is_single_message_clip_request(message):
    return bool(re.search(r"\bclip\s+this\b", message.get("text", ""), re.IGNORECASE))


def get_replied_clip_message(trigger_message, service):
    quoted_message_name = (
        trigger_message.get("quotedMessageMetadata") or {}
    ).get("name")
    if quoted_message_name:
        message = service.spaces().messages().get(
            name=quoted_message_name
        ).execute(num_retries=5)
        trigger_name = trigger_message.get("name")
        if trigger_name and message.get("name") == trigger_name:
            raise ValueError("The clip command cannot be its own reply target.")
        if not has_clip_content(message):
            raise ValueError("The message you replied to has no text or supported images.")
        return message

    thread_name = (trigger_message.get("thread") or {}).get("name")
    if thread_name:
        page_token = None
        thread_messages = []
        while True:
            request = {
                "parent": thread_name.split("/threads/", 1)[0],
                "filter": f"thread.name = {thread_name}",
                "pageSize": 1000,
                "orderBy": "createTime asc",
            }
            if page_token:
                request["pageToken"] = page_token
            response = service.spaces().messages().list(**request).execute(
                num_retries=5
            )
            thread_messages.extend(response.get("messages", []))
            next_page_token = response.get("nextPageToken")
            if not next_page_token or next_page_token == page_token:
                break
            page_token = next_page_token

        trigger_name = trigger_message.get("name")
        for message in thread_messages:
            if message.get("name") != trigger_name and has_clip_content(message):
                return message

    raise ValueError(
        "I couldn't identify the message you replied to. Reply directly to it, "
        "then say 'Sonny clip this'."
    )


def select_previous_clip_messages(messages, count, trigger_message):
    trigger_name = trigger_message.get("name")
    trigger_time = trigger_message.get("createTime")
    if trigger_time:
        trigger_time = datetime.fromisoformat(trigger_time.replace("Z", "+00:00"))

    selected = []
    for message in messages:
        if message.get("name") == trigger_name:
            continue
        message_time = message.get("createTime")
        if trigger_time and (
            not message_time
            or datetime.fromisoformat(message_time.replace("Z", "+00:00")) >= trigger_time
        ):
            continue
        if has_clip_content(message):
            selected.append(message)
            if len(selected) >= count:
                break

    return selected


def image_attachments(message):
    attachments = message.get("attachment") or message.get("attachments") or []
    if isinstance(attachments, dict):
        attachments = [attachments]
    return [
        attachment
        for attachment in attachments
        if is_image_attachment(attachment)
    ]


def is_image_attachment(attachment):
    content_type = (attachment.get("contentType") or "").split(";", 1)[0].strip().lower()
    if content_type.startswith("image/"):
        return True

    content_name = attachment.get("contentName") or ""
    guessed_type = mimetypes.guess_type(content_name)[0] or ""
    return guessed_type.startswith("image/")


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
    match = re.search(
        r"\bclip(?:\s+(?:that|this))?(?:\s+--force)?\s+(\d+)\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return 1

    try:
        count = max(1, int(match.group(1)))
    except ValueError:
        return 1

    return count


def build_clip_post_bodies(clip_message, uploaded_attachments, max_attachments=20):
    if max_attachments < 1:
        raise ValueError("max_attachments must be positive.")

    text_parts = split_clip_text(clip_message)
    attachment_groups = [
        uploaded_attachments[index:index + max_attachments]
        for index in range(0, len(uploaded_attachments), max_attachments)
    ]
    part_count = max(len(text_parts), len(attachment_groups), 1)
    bodies = []
    for index in range(part_count):
        text = text_parts[index] if index < len(text_parts) else ""
        if part_count > 1:
            text = f"Clip part {index + 1}/{part_count}\n{text}"
        if not text:
            text = f"Additional clipped images (part {index + 1}/{part_count})"

        body = {"text": text}
        if index < len(attachment_groups):
            body["attachment"] = attachment_groups[index]
        bodies.append(body)

    return bodies


def has_clip_content(message):
    return bool((message.get("text") or "").strip() or image_attachments(message))
