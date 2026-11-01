
import os
import json
import time
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

                if is_bot_mentioned(msg) and is_summary_request(msg):
                    print("\nSummary request detected!")
                    handle_request()
                    print("\nWaiting for requests...\n")

        except Exception as error:
            print("Error while checking messages:", error)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    listen()
