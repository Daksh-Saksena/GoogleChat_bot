
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly"
]

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

response = service.spaces().list(
    pageSize=100
).execute()

spaces = response.get("spaces", [])

print("\nYOUR GOOGLE CHAT SPACES\n")

for space in spaces:
    print("Name:", space.get("displayName"))
    print("Space ID:", space.get("name"))
    print("Type:", space.get("spaceType"))
    print("-" * 40)
