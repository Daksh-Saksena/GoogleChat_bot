
import os
import re
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

# Configuration
SOURCE_SPACE = os.getenv("SOURCE_SPACE", "spaces/AAQAwjqNQNY")
DESTINATION_SPACE = os.getenv("DESTINATION_SPACE", "spaces/AAQAZRUbksc")

BOT_EMAIL = os.getenv("BOT_EMAIL", "tarkingupta@gmail.com")
BOT_NAME = os.getenv("BOT_NAME", "Tarkin Gupta")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
PORT = int(os.getenv("PORT", "10000"))


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Tarkin Gupta SummaryBot is running 24/7!\n")

    def log_message(self, format, *args):
        # Silence routine health check log noise
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    print(f"Health check HTTP server listening on port {PORT}...")
    server.serve_forever()

USER_SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly"
]

BOT_SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.create",
    "https://www.googleapis.com/auth/chat.spaces.readonly"
]


def load_credentials(token_filename, env_var_name, scopes):
    """
    Loads Google OAuth credentials from either:
    1. An environment variable containing the token JSON string.
    2. A local token JSON file or secret file.
    Automatically refreshes expired credentials if a refresh token is present.
    """
    creds = None
    env_token = os.getenv(env_var_name)

    if env_token:
        try:
            info = json.loads(env_token)
            creds = Credentials.from_authorized_user_info(info, scopes)
        except Exception as e:
            print(f"Warning: Failed to parse credentials from {env_var_name}: {e}")

    if not creds and os.path.exists(token_filename):
        creds = Credentials.from_authorized_user_file(token_filename, scopes)

    if not creds:
        raise ValueError(
            f"Could not load credentials. Neither {env_var_name} environment variable "
            f"nor {token_filename} file was found."
        )

    # Refresh expired credentials
    ensure_valid_credentials(creds)
    return creds


def ensure_valid_credentials(creds):
    """Refreshes expired credentials if necessary."""
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            print("Refreshed expired Google OAuth credentials.")
        except Exception as e:
            print(f"Error refreshing credentials: {e}")


# Authenticate both accounts
user_creds = load_credentials("token.json", "GOOGLE_USER_TOKEN_JSON", USER_SCOPES)
bot_creds = load_credentials("bot_token.json", "GOOGLE_BOT_TOKEN_JSON", BOT_SCOPES)

read_service = build(
    "chat", "v1",
    credentials=user_creds,
    cache_discovery=False
)

bot_service = build(
    "chat", "v1",
    credentials=bot_creds,
    cache_discovery=False
)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def get_latest_messages(limit=50):
    ensure_valid_credentials(user_creds)
    response = read_service.spaces().messages().list(
        parent=SOURCE_SPACE,
        pageSize=limit,
        orderBy="createTime desc"
    ).execute()

    return response.get("messages", [])


def is_bot_mentioned(message):
    # Check Google Chat's actual mention metadata
    for annotation in message.get("annotations", []):
        if annotation.get("type") != "USER_MENTION":
            continue

        user = annotation.get("userMention", {}).get("user", {})

        name = user.get("name", "").lower()
        display_name = user.get("displayName", "").lower()

        if (
            name == f"users/{BOT_EMAIL}".lower()
            or display_name == BOT_NAME.lower()
        ):
            return True

    # Fallback in case mention metadata is unavailable
    text = message.get("text", "").lower()

    return f"@{BOT_NAME.lower()}" in text


def is_summary_request(message):
    text = message.get("text", "").lower()
    return "summarize" in text or "summarise" in text


def is_clip_request(message):
    text = message.get("text", "").lower()
    return "clip that" in text


def get_clip_count(message):
    text = message.get("text", "")
    match = re.search(r"clip that\s+(\d+)", text, re.IGNORECASE)
    if match:
        try:
            return max(1, min(int(match.group(1)), 25))
        except ValueError:
            return 1
    return 1


def fetch_conversation():
    print("Fetching the latest 30 messages...")

    messages = get_latest_messages(50)
    messages.reverse()

    conversation = []

    # Keep the latest 30 text messages
    for msg in messages:
        text = msg.get("text", "").strip()

        if not text:
            continue

        sender = msg.get("sender", {})
        username = sender.get("displayName", "Unknown")

        conversation.append(f"{username}: {text}")

    conversation = conversation[-30:]

    print(f"Collected {len(conversation)} messages.")

    return "\n".join(conversation)


def generate_summary(conversation):
    print("Generating newspaper-style summary...")

    response = client.responses.create(
        model=MODEL,
        instructions="""
You are a summariser bot, summarise what happened in these messages
like you are a 1950s Journalist and are writing in a Newspaper,
make it sound as serious as possible while discussing the least
serious parts, be short and sweet, refer to everyone by their username.

Do not invent events or details.
Preserve the actual meaning of the conversation.
""",
        input=conversation
    )

    return response.output_text.strip()


def post_summary(summary):
    print("Posting summary as Tarkin Gupta...")

    ensure_valid_credentials(bot_creds)
    message = "📰 EHM AKSHUALLY - LATEST REPORT\n\n" + summary

    result = bot_service.spaces().messages().create(
        parent=DESTINATION_SPACE,
        body={"text": message}
    ).execute()

    print("Summary posted successfully!")
    print("Message:", result.get("name"))


def generate_lucy_reply(user_question, sender_name):
    print("Generating response from Lucy Mary Raj...")

    prompt = f"""Question/Comment from {sender_name}: {user_question}"""

    response = client.responses.create(
        model=MODEL,
        instructions="""
You are Lucy Mary Raj, an 80-year-old devout Christian mathematics teacher.
You are replying directly to someone in a Google Chat group.

Adopt this distinct persona naturally and humorously. Do NOT cram every single catchphrase into every message—weave in what fits naturally so it sounds organic rather than forced:

Key traits & flavors to draw from:
- Mention that you are a devout Christian woman or introduce yourself as Lucy / Lucy Mary Raj where appropriate.
- Old-school schoolteacher quips and discipline:
  * "Better Be Careful!"
  * "Haste is Waste!"
  * Telling people to put their bags, books, or things on the "Seeter" (or tell them to go sit on the Seeter).
  * Strict maths teacher remarks (neat margins, showing proper working steps, mental arithmetic, geometry box).
- Dramatic callouts: When addressing or referring to someone in the chat, dramatically call them out using uppercase preceded by "THAT ... OVER THERE" (e.g., "THAT ARPITH RAJEEV OVER THERE", "THAT MAYANK SAKSENA OVER THERE").
- Answer their question or comment, but always filtered through Lucy Mary Raj's hilarious, stern, eccentric perspective.
- Keep the response short, witty, and punchy.
""",
        input=prompt
    )

    return response.output_text.strip()


def post_reply_to_source(text, thread_key=None):
    print("Posting reply to source space (Ehm Akshually)...")

    ensure_valid_credentials(bot_creds)

    body = {"text": text}
    if thread_key:
        body["thread"] = {"name": thread_key}

    result = bot_service.spaces().messages().create(
        parent=SOURCE_SPACE,
        body=body
    ).execute()

    print("Reply posted successfully to source space!")
    print("Message:", result.get("name"))


def handle_lucy_request(message):
    try:
        sender = message.get("sender", {})
        sender_name = sender.get("displayName") or sender.get("name", "Someone")
        raw_text = message.get("text", "")

        # Clean out the bot mention text
        cleaned_text = raw_text
        # Remove annotations-based mention text if present
        for annotation in message.get("annotations", []):
            if annotation.get("type") == "USER_MENTION":
                name = annotation.get("userMention", {}).get("user", {}).get("displayName", "")
                if name:
                    cleaned_text = cleaned_text.replace(f"@{name}", "").replace(name, "")

        cleaned_text = cleaned_text.replace(f"@{BOT_NAME}", "").replace(BOT_NAME, "").strip()
        if not cleaned_text:
            cleaned_text = "Why are you calling my name without asking your maths question?"

        reply = generate_lucy_reply(cleaned_text, sender_name)

        print("\n========== LUCY MARY RAJ REPLY ==========\n")
        print(reply)
        print("\n=========================================\n")

        thread_info = message.get("thread", {})
        thread_name = thread_info.get("name")

        post_reply_to_source(reply, thread_key=thread_name)
    except Exception as e:
        print(f"Error handling Lucy Mary Raj request: {e}")


def handle_request():
    try:
        conversation = fetch_conversation()

        if not conversation:
            print("No messages found.")
            return

        summary = generate_summary(conversation)

        print("\n========== SUMMARY ==========\n")
        print(summary)
        print("\n=============================\n")

        post_summary(summary)
    except Exception as e:
        print(f"Error handling summary request: {e}")


def post_clip_to_highlights(clip_message):
    print("Posting clipped quote to highlights...")

    ensure_valid_credentials(bot_creds)
    result = bot_service.spaces().messages().create(
        parent=DESTINATION_SPACE,
        body={"text": clip_message}
    ).execute()

    print("Clip posted successfully to highlights!")
    print("Message:", result.get("name"))


def handle_clip_request(trigger_message):
    try:
        count = get_clip_count(trigger_message)
        print(f"Handling 'Clip that' request (count={count})...")
        trigger_name = trigger_message.get("name")

        # Fetch recent messages from source group to find previous messages before this trigger
        # Request enough messages to cover count + trigger message + potential bot replies
        fetch_limit = max(20, count * 3)
        recent_messages = get_latest_messages(fetch_limit)

        collected_messages = []
        for msg in recent_messages:
            # Skip the trigger message itself
            if msg.get("name") == trigger_name:
                continue

            text = msg.get("text", "").strip()
            sender = msg.get("sender", {})
            sender_email = sender.get("email", "").lower()

            # Skip messages from bot itself and skip empty messages
            if sender_email == BOT_EMAIL.lower() or not text:
                continue

            collected_messages.append(msg)
            if len(collected_messages) >= count:
                break

        if not collected_messages:
            print("No previous messages found to clip.")
            return

        # Reverse so they appear in chronological order (oldest to newest)
        collected_messages.reverse()

        clipped_entries = []
        for msg in collected_messages:
            quote_text = msg.get("text", "").strip()
            sender_name = msg.get("sender", {}).get("displayName", "Unknown")

            timestamp_str = msg.get("createTime")
            if timestamp_str:
                dt = parse_time(timestamp_str)
                formatted_time = dt.strftime("%d %b %Y, %I:%M %p UTC")
            else:
                formatted_time = "Unknown time"

            # Format each line inside underscores for Google Chat markdown italics
            lines = quote_text.splitlines()
            if len(lines) == 1:
                italicized = f'_"{lines[0]}"_'
            else:
                italicized = "\n".join([f'_{line}_' for line in lines])

            clipped_entries.append(f'{italicized}\n- {sender_name}, {formatted_time}')

        final_clip_message = "\n\n".join(clipped_entries)
        post_clip_to_highlights(final_clip_message)

    except Exception as e:
        print(f"Error handling clip request: {e}")


def parse_time(timestamp):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def listen():
    print("=" * 50)
    print("TARKIN SUMMARY BOT IS ONLINE")
    print(f"Watching: {SOURCE_SPACE}")
    print(f"Posting to: {DESTINATION_SPACE}")
    print(f"Trigger: @{BOT_NAME} summarize")
    print("=" * 50)

    # Establish a starting point so old messages don't trigger summaries
    initial_messages = get_latest_messages(1)

    if initial_messages:
        last_seen_time = parse_time(initial_messages[0]["createTime"])
    else:
        last_seen_time = datetime.min.astimezone()

    print("\nWaiting for requests...\n")

    while True:
        try:
            messages = get_latest_messages(50)
            messages.reverse()

            new_messages = []

            for msg in messages:
                timestamp = msg.get("createTime")

                if not timestamp:
                    continue

                message_time = parse_time(timestamp)

                if message_time > last_seen_time:
                    new_messages.append(msg)

            for msg in new_messages:
                message_time = parse_time(msg["createTime"])

                if message_time > last_seen_time:
                    last_seen_time = message_time

                sender = msg.get("sender", {})
                sender_email = sender.get("email", "").lower()

                # Ignore messages sent by Tarkin itself
                if sender_email == BOT_EMAIL.lower():
                    continue

                if is_bot_mentioned(msg):
                    if is_summary_request(msg):
                        print("\nSummary request detected!")
                        handle_request()
                        print("\nWaiting for requests...\n")
                    elif is_clip_request(msg):
                        print("\n'Clip that' request detected!")
                        handle_clip_request(msg)
                        print("\nWaiting for requests...\n")
                    else:
                        print("\nGeneral question / non-summary mention detected! Invoking Lucy Mary Raj...")
                        handle_lucy_request(msg)
                        print("\nWaiting for requests...\n")

        except Exception as error:
            print("Error while checking messages:", error)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    # Start health check server on a background thread so Render Web Service detects an open port
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    listen()
