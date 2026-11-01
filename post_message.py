
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.create"
]

SPACE_NAME = "spaces/AAQAwjqNQNY"


def send_message(text):
    creds = Credentials.from_authorized_user_file(
        "token.json",
        SCOPES
    )

    service = build(
        "chat",
        "v1",
        credentials=creds,
        cache_discovery=False
    )

    response = service.spaces().messages().create(
        parent=SPACE_NAME,
        body={
            "text": text
        }
    ).execute()

    print("Message successfully posted!")
    print("Message ID:", response.get("name"))

    return response


if __name__ == "__main__":
    message = input("Enter a test message to send: ")
    send_message(message)
