
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly"
]

SPACE_NAME = "spaces/AAQAwjqNQNY"

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

# IMPORTANT: Fetch NEWEST 30 messages first
response = service.spaces().messages().list(
    parent=SPACE_NAME,
    pageSize=30,
    orderBy="createTime desc"
).execute()

messages = response.get("messages", [])

# Reverse to display oldest -> newest
messages.reverse()

print("\n====== EHM AKSHUALLY: LATEST 30 MESSAGES ======\n")

conversation = []

for msg in messages:
    sender = msg.get("sender", {})
    name = sender.get("displayName") or sender.get("name", "Unknown")
    timestamp = msg.get("createTime", "")
    text = msg.get("text", "")

    if text:
        conversation.append(
            f"[{timestamp}] {name}: {text}"
        )
        print(conversation[-1])

print("\n====== FETCH COMPLETE ======")
print(f"Messages retrieved: {len(messages)}")
print(f"Text messages: {len(conversation)}")

if messages:
    print("Oldest fetched:", messages[0].get("createTime"))
    print("Newest fetched:", messages[-1].get("createTime"))
