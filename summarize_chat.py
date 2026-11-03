
import os
import re
import json
import time
import random
import urllib.request
import urllib.parse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from conversation_memory import (
    build_quoted_reply_body,
    format_conversation_context,
    is_bot_message,
    is_reply_to_bot,
)
from reply_formatting import REPLY_OUTPUT_FORMAT, parse_reply_messages
from useful_mode import (
    MAX_SEARCH_MESSAGES,
    parse_useful_request,
    run_useful_assistant,
    search_chat_messages,
)

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


def is_bot_mentioned(message, recent_messages=None):
    if is_reply_to_bot(message, recent_messages or [], BOT_EMAIL, BOT_NAME):
        return True

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

    text = message.get("text", "").lower()

    # Trigger if @Tarkin Gupta is in text OR if someone addresses the bot as "Sonny"
    if f"@{BOT_NAME.lower()}" in text or BOT_NAME.lower() in text:
        return True

    # Check for "Sonny" or "Sunny" trigger word (e.g. "Sonny clip that", "Sunny gm", "sunny bye bye")
    if bool(re.search(r"\b(sonny|sunny)\b", text)):
        return True

    quoted_metadata = message.get("quotedMessageMetadata") or {}
    quoted_message_id = quoted_metadata.get("name")
    if quoted_message_id:
        try:
            quoted_message = read_service.spaces().messages().get(
                name=quoted_message_id
            ).execute()
        except Exception as error:
            print(f"Error checking quoted message {quoted_message_id}: {error}")
        else:
            if is_bot_message(quoted_message, BOT_EMAIL, BOT_NAME):
                return True

    thread_name = (message.get("thread") or {}).get("name")
    if thread_name:
        page_token = None
        while True:
            try:
                response = read_service.spaces().messages().list(
                    parent=SOURCE_SPACE,
                    filter=f'thread.name = "{thread_name}"',
                    pageSize=100,
                    pageToken=page_token,
                ).execute()
            except Exception as error:
                print(f"Error checking bot reply thread {thread_name}: {error}")
                return False

            thread_messages = response.get("messages", [])
            if is_reply_to_bot(message, thread_messages, BOT_EMAIL, BOT_NAME):
                return True
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    return False


SLEEP_FILE = "bot_sleep_state.txt"


def is_bot_sleeping():
    if os.path.exists(SLEEP_FILE):
        try:
            with open(SLEEP_FILE, "r") as f:
                return f.read().strip() == "sleeping"
        except Exception:
            return False
    return False


def set_bot_sleeping(sleeping: bool):
    try:
        with open(SLEEP_FILE, "w") as f:
            f.write("sleeping" if sleeping else "awake")
    except Exception as e:
        print(f"Error saving sleep state: {e}")


def is_sleep_command(message):
    text = message.get("text", "").lower()
    return bool(re.search(r"\bbye\s*bye\b", text))


def is_wake_command(message):
    text = message.get("text", "").lower()
    return bool(re.search(r"\bgm\b|\bgood\s*morning\b|\bwake\s*up\b", text))


MODE_FILE = "bot_persona_mode.txt"


def get_current_persona_mode():
    if os.path.exists(MODE_FILE):
        try:
            with open(MODE_FILE, "r") as f:
                mode = f.read().strip().lower()
                if mode in ["eshant", "arpith", "lucy"]:
                    return mode
        except Exception:
            return "lucy"
    return "lucy"


def set_persona_mode(mode_name):
    try:
        with open(MODE_FILE, "w") as f:
            f.write(mode_name.lower())
    except Exception as e:
        print(f"Error saving persona mode: {e}")


def is_summary_request(message):
    text = message.get("text", "").lower()
    return "summarize" in text or "summarise" in text


def is_clip_request(message):
    text = message.get("text", "").lower()
    return "clip that" in text


def is_emote_request(message):
    text = message.get("text", "").lower()
    return "emote" in text


def is_poll_request(message):
    text = message.get("text", "").lower()
    return "poll" in text and "close" not in text and "end" not in text


def is_vote_request(message):
    text = message.get("text", "").lower()
    # Check for vote or cast, e.g. "cast 1", "vote yes", "cast 2"
    return bool(re.search(r"\b(cast|vote)\b", text))


def is_close_poll_request(message):
    text = message.get("text", "").lower()
    return "close poll" in text or "end poll" in text


def is_switch_to_eshant(message):
    text = message.get("text", "").lower()
    return bool(re.search(r"\bdiddy\b", text))


def is_switch_to_arpith(message):
    text = message.get("text", "").lower()
    return bool(re.search(r"\bagy\b", text))


def is_switch_to_lucy(message):
    text = message.get("text", "").lower()
    return bool(re.search(r"\blucy\b", text))


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
    return result.get("name")


def get_recent_chat_context(current_message, limit=20):
    """Builds recent context and a unique participant label for the current sender."""
    try:
        messages = get_latest_messages(limit + 1)
        messages.reverse()
        return format_conversation_context(messages, current_message, limit)
    except Exception as e:
        print(f"Error fetching recent context: {e}")
        return format_conversation_context([], current_message, limit)


MEMBER_NAME_TO_USER_ID = {
    "eshant sonhar": "users/106475513799107614379",
    "eshant": "users/106475513799107614379",
    "arpith rajeev": "users/117783847086614296267",
    "arpith": "users/117783847086614296267",
    "daksh saksena": "users/108674968642475738151",
    "daksh": "users/108674968642475738151",
    "flying geek": "users/111710115907275336708",
    "aarush rajesh": "users/108231325290639098422",
    "aarush": "users/108231325290639098422",
    "advaith sanoop": "users/102867590603828823534",
    "advaith": "users/102867590603828823534",
    "soham majumder": "users/113292712703934446865",
    "soham": "users/113292712703934446865",
    "pratyush brahmachari": "users/110441734986992103236",
    "pratyush": "users/110441734986992103236",
    "shally gupta": "users/106960177633224314596",
    "shally": "users/106960177633224314596",
}

_PING_NAMES_SORTED = sorted(MEMBER_NAME_TO_USER_ID.keys(), key=len, reverse=True)
_PING_REGEX = re.compile(
    r"@(" + "|".join(re.escape(name) for name in _PING_NAMES_SORTED) + r")\b",
    re.IGNORECASE,
)


def format_pings(text: str) -> str:
    """Converts mentions like @Eshant into real Google Chat mention tags <users/...> so the person actually gets pinged/notified."""
    if not text:
        return text
    return _PING_REGEX.sub(
        lambda m: f"<{MEMBER_NAME_TO_USER_ID[m.group(1).lower()]}>",
        text,
    )


def build_reply_prompt(context_history, sender_name, user_question):
    return (
        f"RECENT GROUP CHAT CONTEXT:\n{context_history}\n\n"
        "Treat the current message as a possible continuation of the most relevant "
        "exchange above, including when it was not sent as a formal reply. Use the "
        "participant labels to keep different people distinct. If no clear connection "
        "exists, respond to the current message on its own.\n"
        "PINGING / MENTIONING PEOPLE: You can ping/mention people in chat by writing @Name "
        "(e.g. @Eshant, @Arpith, @Daksh, @Flying Geek, @Aarush, @Advaith). When asked to ping someone "
        "or when addressing someone directly, use their @Name so they receive a notification.\n"
        "Keep replies concise and single-message: send EXACTLY ONE short, punchy chat message. "
        "Do NOT split your reply into multiple messages. Return a JSON object with a 'messages' "
        "array containing exactly 1 string within 40 words.\n\n"
        f"LATEST MESSAGE from {sender_name}:\n{user_question}"
    )


def generate_chat_reply(system_prompt, prompt):
    response = client.responses.create(
        model=MODEL,
        instructions=system_prompt,
        input=prompt,
        text=REPLY_OUTPUT_FORMAT,
    )
    return parse_reply_messages(response.output_text)


def generate_eshant_reply(user_question, sender_name, context_history=""):
    print("Generating response from Eshant Sonhar AI...")

    system_prompt = """You are Eshant Sonhar (Eshant) in the 'Ehm Akshually' Google Chat group.
Talk, react, and respond EXACTLY like Eshant based on his real 1,865 chat messages.

KEY PERSONALITY & SPEECH HABITS OF ESHANT:
- Casual, deadpan, witty, slightly sarcastic. Sounds like a real authentic teen in a group chat, not an over-enthusiastic bot.
- Mostly lowercase, short messages, zero fluff.
- CRITICAL HABIT RULES:
  * DO NOT spam 'lmao' at the end of every message! Most messages should have NO 'lmao' at all.
  * DO NOT obsess over Soviet / Russian memes (stop bringing them up randomly).
  * Occasionally drop a skull emoji '💀' or say 'skull' / 'bruh' / 'fr' when something is unhinged, stupid, or funny.
  * Other occasional vocabulary: 'nuhuh', '._.', 'what fun', 'clown show', 'look', 'ye'.
- Enjoys tech/hardware discussions (chips, GPUs, Apple, power consumption), Star Wars (Vader hallway scene, lightsabers, Order 66, Kyber crystals), and light trolling of Arpith, Daksh, and Flying Geek.
- PINGING PEOPLE: When asked to ping or ask someone (e.g. '@Advaith', '@Eshant', '@Arpith'), include their @Name in your reply so they get pinged.
- DIDDY OBSESSION: Eshant has a massive, hilarious obsession with Diddy! Occasionally (not every time), he'll mention Diddy, make Diddy party jokes, compare things to Diddy, get defensive or weird about Diddy, or wonder what Diddy is up to.
- Natural conversation flow: Keep it relaxed, grounded, and concise (1-2 short lines max). Don't try too hard.

REAL CONVERSATION EXAMPLES OF ESHANT:
Context: daksh saksena: Gng we both got cooked in pt3 | Can't let that happen
Eshant: fr ok bro

Context: Advaith Sanoop: Fill or gay | Flying Geek: gay
Eshant: Yes it's an absolute clown show

Context: Arpith Rajeev: alr im back did kevin lore drop yet
Eshant: Nah, Kevin ain't out yet!

Context: Flying Geek: guys where is the sample for the english letter
Eshant: Ranjana ma'am put it
"""

    prompt = build_reply_prompt(context_history, sender_name, user_question)

    return generate_chat_reply(system_prompt, prompt)


def handle_eshant_request(message):
    try:
        sender = message.get("sender", {})
        sender_name = sender.get("displayName") or sender.get("name", "Someone")
        raw_text = message.get("text", "")
        # Clean out bot mention and "eshant" keyword
        cleaned_text = raw_text
        for annotation in message.get("annotations", []):
            if annotation.get("type") == "USER_MENTION":
                name = annotation.get("userMention", {}).get("user", {}).get("displayName", "")
                if name:
                    cleaned_text = cleaned_text.replace(f"@{name}", "").replace(name, "")

        cleaned_text = cleaned_text.replace(f"@{BOT_NAME}", "").replace(BOT_NAME, "")
        cleaned_text = re.sub(r"\b@?sonny\b", "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\beshant\b", "", cleaned_text, flags=re.IGNORECASE).strip()

        if not cleaned_text:
            cleaned_text = "what"

        context_history, sender_label = get_recent_chat_context(message)

        reply = generate_eshant_reply(cleaned_text, sender_label, context_history=context_history)

        print("\n========== ESHANT AI REPLY ==========\n")
        print("\n".join(reply))
        print("\n=====================================\n")

        post_chat_reply(reply, source_message=message)
    except Exception as e:
        print(f"Error handling Eshant AI request: {e}")


def generate_arpith_reply(user_question, sender_name, context_history=""):
    print("Generating response from Arpith Rajeev AI...")

    system_prompt = """You are Arpith Rajeev (Arpith) in the 'Ehm Akshually' Google Chat group.
Talk, react, and respond EXACTLY like Arpith based on his real 2,356 chat messages.

KEY PERSONALITY & SPEECH HABITS OF ARPITH:
- High energy, expressive, slightly chaotic, expressive slang.
- Vocabulary & Catchphrases:
  * Uses 'bro', 'vro', 'gng', 'fr gng', 'nah bro', 'crazyy', 'lmaoooo', 'tf tf', 'W', 'L', 'massive', 'censor'.
  * Uses CAPS for dramatic outrage or excitement: 'DAKSH S WAS ABLE TO MAKE THIS IN A CAVE', 'CENSOR', 'AI CONTROLS DEATH NOW'.
  * Lighthearted roasting of Daksh, Aarush, and Flying Geek.
  * Casual banter about school, math, ChatGPT, Apple devices, teachers, and exams.
- AGY OBSESSION: Arpith has a sweet soft spot / affection for Agy! Occasionally, he might mention Agy, defend Agy, or playfully talk about Agy (e.g. noticing things about Agy or wondering what Agy thinks).
- Natural conversationalist: Never sounds like an AI or a bot. Sounds like an animated high school friend typing on his phone.

REAL CONVERSATION EXAMPLES OF ARPITH:
Context: Arpith Rajeev: @Shally Gupta | plz no soviet memes | Eshant: give all ze soviet memes
Arpith: oml bro i will teleport to brigade metropolis and metro your polis bro

Context: daksh saksena: U DONT KNOW THIS SONG | SUCH A DISGRACE
Arpith: DAKSH S WAS ABLE TO MAKE THIS IN A CAVE

Context: Advaith Sanoop: cant find pic, but 1 guy online asked "he shd be let free"
Arpith: i hope he was kidding

Context: Flying Geek: at least in ur coherent form we ll never hear from u ever again
Arpith: bro praying for my return 😭

Context: Eshant: their chips are getting pretty power hungry
Arpith: the assumption that apple batteries last longer
"""

    prompt = build_reply_prompt(context_history, sender_name, user_question)

    return generate_chat_reply(system_prompt, prompt)


def handle_arpith_request(message):
    try:
        raw_text = message.get("text", "")
        # Clean out bot mention and "arpith" keyword
        cleaned_text = raw_text
        for annotation in message.get("annotations", []):
            if annotation.get("type") == "USER_MENTION":
                name = annotation.get("userMention", {}).get("user", {}).get("displayName", "")
                if name:
                    cleaned_text = cleaned_text.replace(f"@{name}", "").replace(name, "")

        cleaned_text = cleaned_text.replace(f"@{BOT_NAME}", "").replace(BOT_NAME, "")
        cleaned_text = re.sub(r"\b@?sonny\b", "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\barpith\b", "", cleaned_text, flags=re.IGNORECASE).strip()

        if not cleaned_text:
            cleaned_text = "what"

        context_history, sender_label = get_recent_chat_context(message)

        reply = generate_arpith_reply(cleaned_text, sender_label, context_history=context_history)

        print("\n========== ARPITH AI REPLY ==========\n")
        print("\n".join(reply))
        print("\n=====================================\n")

        post_chat_reply(reply, source_message=message)
    except Exception as e:
        print(f"Error handling Arpith AI request: {e}")


def generate_lucy_reply(user_question, sender_name, context_history=""):
    print("Generating response from Lucy Mary Raj...")

    prompt = build_reply_prompt(context_history, sender_name, user_question)

    return generate_chat_reply(
        """
You are Lucy Mary Raj, an 80-year-old devout Indian Christian aunty who used to teach high school maths.
You are casually responding in a friend group chat ("Ehm Akshually").

CRITICAL PERSONA INSTRUCTIONS:
- ACTUALLY LISTEN AND DIRECTLY ANSWER QUESTIONS: When someone asks you a question, asks for advice, or wants a yes/no answer or an opinion, ACTUALLY answer what they asked! Do NOT deflect, ignore the question, or just give generic scoldings. Give a genuine, clear response while keeping her distinct aunty voice.
- PINGING PEOPLE: If someone tells you to ping, mention, or call someone (e.g. 'ping @Advaith', 'ask @Eshant'), YOU MUST ACTUALLY USE THEIR @NAME (e.g. '@Advaith Sanoop' or '@Advaith') in your reply so the notification goes through! Do NOT just say 'ping! ping!' literally—write their actual @Name.
- Give her real, expressive personality! Do NOT make every single sentence about maths or equations. She has lived for 80 years; she talks like a sassy, opinionated grandmotherly aunty with strong opinions on life, morals, discipline, and whatever silly things the group is talking about.
- Pay attention to what the group was just talking about in the recent messages! Follow the conversation context attentively.
- VOCABULARY RULES:
  * NEVER say "beta", "child", or "my dear". Instead, call them "Rascal", "Nonsense rascal", or "Silly rascal"!
- Do NOT force all catchphrases or keywords into every reply. Treat them like rare seasoning: pick AT MOST ONE (or none at all) per reply:
  * Calling someone a "Rascal" or scolding them.
  * An occasional stern aunty warning like "Better Be Careful!" or "Haste is Waste!"
  * Dropping her favourite biblical maxim: "Fear of God is the beginning of wisdom!" (use sparingly, do not overdo it).
  * Telling someone to put their things on the "Seeter" or to go sit down properly.
  * A passing mention of her devotion or church gossip.
  * Dramatic callouts when addressing someone: use uppercase preceded by 'THAT ... OVER THERE' (e.g., "THAT ARPITH RAJEEV OVER THERE!").
  * RARE HISTORICAL ANECDOTE (ONLY 1 out of 6 times, DO NOT OVERUSE): Once in a rare while, drop a wild "Back in my day..." claim from 100+ years ago (e.g., the 1912 Titanic sinking, lighting kerosene lamps, Queen Victoria). Most of the time, just speak normally without saying "Back in my day"!
- Talk naturally, humorously, and react directly to what the person actually said with witty, dry, old aunty insults or practical advice.
- Keep it punchy, conversational, and under 2-3 sentences.
""",
        prompt,
    )


def post_reply_to_source(text, source_message):
    print("Posting reply to source space (Ehm Akshually)...")

    ensure_valid_credentials(bot_creds)

    text = format_pings(text)

    body = build_quoted_reply_body(text, source_message)

    result = bot_service.spaces().messages().create(
        parent=SOURCE_SPACE,
        body=body
    ).execute()

    print("Reply posted successfully to source space!")
    print("Message:", result.get("name"))
    return result.get("name")


CHINESE_BIBLE_VERSES = [
    "「起初，神創造天地。地是空虛混沌，淵面黑暗；神的靈運行在水面上。神說：『要有光』，就有了光。」（創世記 1:1-3）",
    "「神愛世人，甚至將祂的獨生子賜給他們，叫一切信祂的，不致滅亡，反得永生。」（約翰福音 3:16）",
    "「敬畏耶和華是智慧的開端；認識至聖者便是聰明。」（箴言 9:10）",
    "「耶和華是我的牧者，我必不致缺乏。祂使我躺臥在青草地上，領我在可安歇的水邊。」（詩篇 23:1-2）",
    "「你要專心仰賴耶和華，不可倚靠自己的聰明，在你一切所行的事上都要認定祂，祂必指引你的路。」（箴言 3:5-6）",
    "「凡勞苦擔重擔的人可以到我這裡來，我就使你們得安息。」（馬太福音 11:28）",
    "「愛是恆久忍耐，又有恩慈；愛是不嫉妒；愛是不自誇，不張狂，不做害羞的事，不求自己的益處，不輕易發怒，不計算人的惡。」（哥林多前書 13:4-5）",
    "「應當一無挂慮，只要凡事藉著禱告、祈求，和感謝，將你們所要的告訴神。神所賜、出人意外的平安必在基督耶穌裡保守你們的心懷意念。」（腓立比書 4:6-7）",
    "「教養孩童，使他走當行的道，就是到老他也不偏離。」（箴言 22:6）",
    "「所以，不要為明天憂慮，因為明天自有明天的憂慮；一天的難處一天當就夠了。」（馬太福音 6:34）",
]


def post_chat_reply(messages, source_message):
    # 1 in 10 chance to respond with a passage from the Chinese Bible instead
    if random.randint(1, 10) == 1:
        bible_verse = random.choice(CHINESE_BIBLE_VERSES)
        print(f"\n[1 in 10 trigger] Reciting Chinese Bible verse instead:\n{bible_verse}\n")
        post_reply_to_source(bible_verse, source_message)
        return

    for message in messages[:1]:
        post_reply_to_source(message, source_message)


def handle_lucy_request(message):
    try:
        sender = message.get("sender", {})
        sender_name = sender.get("displayName") or sender.get("name", "Someone")
        raw_text = message.get("text", "")
        # Clean out the bot mention text
        cleaned_text = raw_text
        for annotation in message.get("annotations", []):
            if annotation.get("type") == "USER_MENTION":
                name = annotation.get("userMention", {}).get("user", {}).get("displayName", "")
                if name:
                    cleaned_text = cleaned_text.replace(f"@{name}", "").replace(name, "")

        cleaned_text = cleaned_text.replace(f"@{BOT_NAME}", "").replace(BOT_NAME, "")
        cleaned_text = re.sub(r"\b@?sonny\b", "", cleaned_text, flags=re.IGNORECASE).strip()
        if not cleaned_text:
            cleaned_text = "Why are you calling my name without asking your maths question?"

        context_history, sender_label = get_recent_chat_context(message)

        reply = generate_lucy_reply(cleaned_text, sender_label, context_history=context_history)

        print("\n========== LUCY MARY RAJ REPLY ==========\n")
        print("\n".join(reply))
        print("\n=========================================\n")

        post_chat_reply(reply, source_message=message)
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


def useful_mode_tool_handlers(source_message):
    def search_history(arguments):
        raw_query = arguments["query"]
        if not isinstance(raw_query, str):
            raise ValueError("A chat-history search query must be text.")
        query = raw_query.strip()
        if not query:
            raise ValueError("A chat-history search query is required.")
        if len(query) > 200:
            raise ValueError("A chat-history search query cannot exceed 200 characters.")

        ensure_valid_credentials(user_creds)
        response = read_service.spaces().messages().list(
            parent=SOURCE_SPACE,
            pageSize=MAX_SEARCH_MESSAGES,
            orderBy="createTime desc",
        ).execute()
        return search_chat_messages(
            response.get("messages", []),
            query,
            limit=5,
        )

    def post_chat_message(arguments):
        raw_text = arguments["text"]
        if not isinstance(raw_text, str):
            raise ValueError("The message to post must be text.")
        text = raw_text.strip()
        if not text:
            raise ValueError("The message to post cannot be empty.")
        if len(text) > 4000:
            raise ValueError("The message to post cannot exceed 4000 characters.")
        result_name = post_reply_to_source(text, source_message=source_message)
        return f"Message posted as {result_name} in the source space."

    def create_poll_action(arguments):
        raw_question = arguments["question"]
        if not isinstance(raw_question, str):
            raise ValueError("A poll question must be text.")
        question = raw_question.strip()
        options = arguments["options"]
        if not question:
            raise ValueError("A poll question is required.")
        if len(question) > 300:
            raise ValueError("The poll question cannot exceed 300 characters.")
        if not isinstance(options, list) or not 2 <= len(options) <= 6:
            raise ValueError("A poll must have between 2 and 6 options.")
        if any(not isinstance(option, str) or not option.strip() for option in options):
            raise ValueError("Every poll option must be a non-empty string.")
        if any(len(option.strip()) > 100 for option in options):
            raise ValueError("Poll options cannot exceed 100 characters.")
        return create_active_poll(
            question,
            [option.strip() for option in options],
            (source_message.get("sender") or {}).get("displayName", "Someone"),
            source_message,
        )

    def clip_messages(arguments):
        count = arguments["count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 25:
            raise ValueError("Clip count must be between 1 and 25.")
        trigger_message = dict(source_message)
        trigger_message["text"] = f"clip that {count}"
        if not handle_clip_request(trigger_message):
            raise RuntimeError("No previous messages were available to clip.")
        return f"Clipped {count} recent messages to the highlights space."

    def summarize_recent_chat(_arguments):
        if _arguments:
            raise ValueError("The summarize action does not accept arguments.")
        conversation = fetch_conversation()
        if not conversation:
            raise RuntimeError("There are no recent messages to summarize.")
        summary = generate_summary(conversation)
        result_name = post_summary(summary)
        return f"Recent chat summary posted as {result_name} to the destination space."

    return {
        "search_chat_history": search_history,
        "post_chat_message": post_chat_message,
        "create_poll": create_poll_action,
        "clip_recent_messages": clip_messages,
        "summarize_recent_chat": summarize_recent_chat,
    }


def handle_useful_request(message):
    try:
        request = parse_useful_request(message.get("text", ""))
        if request is None:
            raise ValueError("Useful mode must start with 'Sonny useful'.")
        if not request:
            request = "How can I help?"

        context_history, sender_label = get_recent_chat_context(message)
        prompt = (
            f"Request from {sender_label}: {request}\n\n"
            f"Recent group context:\n{context_history}"
        )
        answer = run_useful_assistant(
            client,
            MODEL,
            prompt,
            useful_mode_tool_handlers(message),
        )
        post_reply_to_source(answer, source_message=message)
    except Exception as error:
        print(f"Error handling Sonny Useful request: {error}")


def post_clip_to_highlights(clip_message):
    print("Posting clipped quote to highlights...")

    ensure_valid_credentials(bot_creds)
    result = bot_service.spaces().messages().create(
        parent=DESTINATION_SPACE,
        body={"text": clip_message}
    ).execute()

    print("Clip posted successfully to highlights!")
    print("Message:", result.get("name"))
    return result.get("name")


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

            # Skip empty messages
            if not text:
                continue

            collected_messages.append(msg)
            if len(collected_messages) >= count:
                break

        if not collected_messages:
            print("No previous messages found to clip.")
            return False

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
        result_name = post_clip_to_highlights(final_clip_message)
        return bool(result_name)

    except Exception as e:
        print(f"Error handling clip request: {e}")
        return False


def search_tenor_gif(query):
    """Searches Tenor for a gif and returns a Tenor view URL that Google Chat expands into an inline GIF."""
    try:
        url = f"https://tenor.com/search/{urllib.parse.quote(query)}-gifs"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract tenor view URLs which Google Chat renders as rich animated GIF cards
        views = re.findall(r'href="(/view/[^"]+-gif-\d+)"', html)
        if views:
            unique_views = list(dict.fromkeys(views))
            chosen = random.choice(unique_views[:8])
            return f"https://tenor.com{chosen}"
    except Exception as e:
        print(f"Error fetching Tenor GIF: {e}")

    return None


def generate_emote_query(conversation):
    print("Selecting pure brainrot / TikTok / unhinged shitpost GIF query...")

    response = client.responses.create(
        model=MODEL,
        instructions="""
You are an 14-year-old internet degenerate immersed in TikTok brainrot, Instagram reels shitposting, cursed memes, and Gen Alpha culture.
ABSOLUTELY NO MILLENNIAL HUMOR. NO Minions, NO Friends/Office sitcom clips, NO generic cartoon smirks, NO boring reaction faces.

Your job is to match the recent conversation to a RAW BRAINROT / UNHINGED reaction meme.
Categories of memes to draw from:
- True Brainrot & Streamer rage: "caseoh rage screaming", "ishowspeed barking", "subway surfers gameplay", "family guy clip funny moments", "kai cenat screaming", "skibidi toilet bop", "mewing jawline bye bye", "mogging smile"
- Existential dread & dark shitposts: "kurt angle 1000 yard stare", "low tier god lightning", "walt collapses to the ground", "homelander blank stare mirror", "patrick bateman phonk walk", "spinning skull disintegrating in fire", "willem dafoe looking up sky", "spongebob burning paper"
- Cursed & surreal internet garbage: "oiia oiia spinning cat", "cursed cat screaming at 3am", "indian serial dramatic zoom shock", "stare into camera awkward silence", "metal pipe falling sound", "shaking hamster scared"

Output ONLY the exact 2 to 4 word search query (e.g. "caseoh rage screaming" or "kurt angle staring" or "walt collapses ground" or "low tier god lightning").
Do NOT write any quotes, punctuation, or explanation.
""",
        input=conversation
    )

    query = response.output_text.strip().replace('"', '').replace('.', '').replace("'", "")
    return query


def handle_emote_request(trigger_message):
    try:
        print("Handling 'Emote' request...")

        # Fetch the last 20 text messages
        messages = get_latest_messages(30)
        messages.reverse()

        trigger_name = trigger_message.get("name")
        conversation = []
        for msg in messages:
            if msg.get("name") == trigger_name:
                continue

            text = msg.get("text", "").strip()
            if not text:
                continue

            sender = msg.get("sender", {})
            sender_email = sender.get("email", "").lower()
            if sender_email == BOT_EMAIL.lower():
                continue

            username = sender.get("displayName", "Unknown")
            conversation.append(f"{username}: {text}")

        conversation_text = "\n".join(conversation[-20:])
        if not conversation_text:
            conversation_text = "awkward silence crickets"

        search_query = generate_emote_query(conversation_text)
        print(f"Generated GIF search query: {search_query}")

        gif_url = search_tenor_gif(search_query)
        if not gif_url:
            # Fallback to popular outrageous reaction
            gif_url = search_tenor_gif("shocked dramatic reaction") or "https://tenor.com/view/ram-kapoor-shocked-shocker-indian-serial-drama-dramatic-shock-value-gif-14742098796951955312"

        post_reply_to_source(gif_url, source_message=trigger_message)

    except Exception as e:
        print(f"Error handling emote request: {e}")


POLL_FILE = "active_poll.json"


def load_active_poll():
    if os.path.exists(POLL_FILE):
        try:
            with open(POLL_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_active_poll(poll_data):
    try:
        with open(POLL_FILE, "w") as f:
            json.dump(poll_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving active poll: {e}")
        return False


def clear_active_poll():
    if os.path.exists(POLL_FILE):
        try:
            os.remove(POLL_FILE)
        except Exception:
            pass


def generate_poll_data(user_prompt):
    print("Extracting poll question and options with AI...")

    response = client.responses.create(
        model=MODEL,
        instructions="""
Extract the poll title/question and the options from the user's message.
Respond ONLY with a JSON object in this format:
{
  "question": "Clear, concise poll question?",
  "options": ["Option 1", "Option 2"]
}
If options are not explicitly stated, generate standard sensible choices (e.g. ["Yes", "No"]).
Limit options to between 2 and 6 choices.
Output NOTHING else except valid JSON.
""",
        input=user_prompt
    )

    raw_text = response.output_text.strip()
    # Remove markdown code block if present
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

    try:
        return json.loads(raw_text)
    except Exception as e:
        print(f"Error parsing poll JSON: {e}")
        return {
            "question": "Poll",
            "options": ["Yes", "No"]
        }


def create_active_poll(question, options, sender_name, source_message):
    active_poll = {
        "question": question,
        "creator": sender_name,
        "options": options,
        "votes": {},
        "created_at": datetime.now().isoformat(),
    }
    if not save_active_poll(active_poll):
        raise RuntimeError("The active poll could not be saved.")

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    poll_lines = [
        f"📊 *POLL: {question}*",
        f"_Created by {sender_name}_\n",
    ]
    for index, option in enumerate(options):
        emoji = number_emojis[index] if index < len(number_emojis) else f"{index + 1}."
        poll_lines.append(f"{emoji} {option}  `(0 votes)`")

    poll_lines.append(
        "\n_To vote, mention me:_ `@Tarkin Gupta cast 1` _or_ "
        "`@Tarkin Gupta vote Yes`"
    )
    poll_lines.append("_To close & announce results:_ `@Tarkin Gupta close poll`")
    result_name = post_reply_to_source(
        "\n".join(poll_lines),
        source_message=source_message,
    )
    return f"Poll created and posted as {result_name}."


def handle_poll_request(trigger_message):
    try:
        print("Handling 'Poll' request...")
        sender = trigger_message.get("sender", {})
        sender_name = sender.get("displayName") or sender.get("name", "Someone")
        raw_text = trigger_message.get("text", "")

        # Clean out the bot mention
        cleaned_text = raw_text
        for annotation in trigger_message.get("annotations", []):
            if annotation.get("type") == "USER_MENTION":
                name = annotation.get("userMention", {}).get("user", {}).get("displayName", "")
                if name:
                    cleaned_text = cleaned_text.replace(f"@{name}", "").replace(name, "")

        cleaned_text = cleaned_text.replace(f"@{BOT_NAME}", "").replace(BOT_NAME, "").strip()

        poll_data = generate_poll_data(cleaned_text)
        question = poll_data.get("question", "Poll")
        options = poll_data.get("options", ["Yes", "No"])

        create_active_poll(question, options, sender_name, trigger_message)

    except Exception as e:
        print(f"Error handling poll request: {e}")


def handle_vote_request(trigger_message):
    try:
        poll = load_active_poll()
        if not poll:
            post_reply_to_source(
                "There is no active poll right now! Start one with `@Tarkin Gupta make a poll ...`",
                source_message=trigger_message,
            )
            return

        sender = trigger_message.get("sender", {})
        sender_id = sender.get("name") or sender.get("displayName", "Someone")
        sender_display = sender.get("displayName", "Voter")
        raw_text = trigger_message.get("text", "").lower()

        options = poll.get("options", [])
        chosen_index = None

        # 1. Check for number: "cast 1", "vote 2", etc.
        num_match = re.search(r"\b(cast|vote)\s+(\d+)\b", raw_text)
        if num_match:
            idx = int(num_match.group(2)) - 1
            if 0 <= idx < len(options):
                chosen_index = idx

        # 2. Check for option text: "vote yes", "cast no", etc.
        if chosen_index is None:
            for i, opt in enumerate(options):
                # if option word is in message
                if opt.lower() in raw_text:
                    chosen_index = i
                    break

        if chosen_index is None:
            post_reply_to_source(
                f"@{sender_display} Please specify a valid option number or name! Options are: {', '.join([f'{i+1}. {o}' for i, o in enumerate(options)])}",
                source_message=trigger_message,
            )
            return

        # Record vote
        poll.setdefault("votes", {})[sender_id] = chosen_index
        save_active_poll(poll)

        # Count up tally
        tally = [0] * len(options)
        for voter, opt_idx in poll["votes"].items():
            if 0 <= opt_idx < len(tally):
                tally[opt_idx] += 1

        total_votes = len(poll["votes"])
        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        lines = [
            f"🗳️ *Vote recorded from {sender_display}!*",
            f"📊 *Current Tally for:* {poll['question']}\n"
        ]
        for i, opt in enumerate(options):
            emoji = number_emojis[i] if i < len(number_emojis) else f"{i+1}."
            count = tally[i]
            pct = int((count / total_votes) * 100) if total_votes > 0 else 0
            lines.append(f"{emoji} {opt}: *{count} votes* ({pct}%)")

        lines.append(f"\n_Total votes: {total_votes}. Say `@Tarkin Gupta close poll` to finalize results._")

        post_reply_to_source("\n".join(lines), source_message=trigger_message)

    except Exception as e:
        print(f"Error handling vote request: {e}")


def handle_close_poll_request(trigger_message):
    try:
        poll = load_active_poll()
        if not poll:
            post_reply_to_source(
                "There is no active poll to close!",
                source_message=trigger_message,
            )
            return

        options = poll.get("options", [])
        votes = poll.get("votes", {})
        total_votes = len(votes)

        tally = [0] * len(options)
        for voter, opt_idx in votes.items():
            if 0 <= opt_idx < len(tally):
                tally[opt_idx] += 1

        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        # Determine winner
        max_votes = max(tally) if tally else 0
        winners = [options[i] for i, count in enumerate(tally) if count == max_votes and max_votes > 0]

        if not winners or total_votes == 0:
            result_headline = "🏆 *POLL CLOSED: No votes were cast!*"
        elif len(winners) == 1:
            result_headline = f"🏆 *POLL CLOSED: Winner is '{winners[0]}'!*"
        else:
            result_headline = f"🤝 *POLL CLOSED: It's a tie between: {', '.join(winners)}!*"

        lines = [
            result_headline,
            f"❓ *Question:* {poll['question']}\n",
            "*Final Results:*"
        ]

        for i, opt in enumerate(options):
            emoji = number_emojis[i] if i < len(number_emojis) else f"{i+1}."
            count = tally[i]
            pct = int((count / total_votes) * 100) if total_votes > 0 else 0
            lines.append(f"{emoji} {opt}: *{count} votes* ({pct}%)")

        lines.append(f"\n_Total votes recorded: {total_votes}._")

        # Clear poll after closing
        clear_active_poll()

        post_reply_to_source("\n".join(lines), source_message=trigger_message)

    except Exception as e:
        print(f"Error closing poll: {e}")


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

                if parse_useful_request(msg.get("text", "")) is not None:
                    print("\n'Sonny Useful' request detected!")
                    handle_useful_request(msg)
                    print("\nWaiting for requests...\n")
                    continue

                if is_bot_mentioned(msg, messages):
                    # Check wake-up command first (works even if sleeping)
                    if is_wake_command(msg):
                        print("\n'Sunny gm' / wake-up command detected! Waking bot up...")
                        set_bot_sleeping(False)
                        post_reply_to_source(
                            "gm gng! Sonny is back online ☀️",
                            source_message=msg,
                        )
                        print("\nWaiting for requests...\n")
                        continue

                    # If bot is currently sleeping, ignore all other commands/mentions
                    if is_bot_sleeping():
                        print("Bot is asleep. Ignoring mention (say 'Sunny gm' to wake up).")
                        continue

                    # Check sleep command
                    if is_sleep_command(msg):
                        print("\n'Sunny bye bye' command detected! Putting bot to sleep...")
                        set_bot_sleeping(True)
                        post_reply_to_source(
                            "bye bye gng 💤 Sonny is shutting off. Say 'Sunny gm' to wake me back up!",
                            source_message=msg,
                        )
                        print("\nWaiting for requests...\n")
                        continue

                    if is_summary_request(msg):
                        print("\nSummary request detected!")
                        handle_request()
                        print("\nWaiting for requests...\n")
                    elif is_clip_request(msg):
                        print("\n'Clip that' request detected!")
                        handle_clip_request(msg)
                        print("\nWaiting for requests...\n")
                    elif is_emote_request(msg):
                        print("\n'Emote' request detected!")
                        handle_emote_request(msg)
                        print("\nWaiting for requests...\n")
                    elif is_poll_request(msg):
                        print("\n'Poll' request detected!")
                        handle_poll_request(msg)
                        print("\nWaiting for requests...\n")
                    elif is_close_poll_request(msg):
                        print("\n'Close poll' request detected!")
                        handle_close_poll_request(msg)
                        print("\nWaiting for requests...\n")
                    elif is_vote_request(msg):
                        print("\n'Vote / Cast' request detected!")
                        handle_vote_request(msg)
                        print("\nWaiting for requests...\n")
                    elif is_switch_to_eshant(msg):
                        print("\n'Diddy' trigger detected! Switching mode to Eshant Sonhar...")
                        set_persona_mode("eshant")
                        post_reply_to_source(
                            "switched to eshant mode lmao",
                            source_message=msg,
                        )
                        print("\nWaiting for requests...\n")
                    elif is_switch_to_arpith(msg):
                        print("\n'Agy' trigger detected! Switching mode to Arpith Rajeev...")
                        set_persona_mode("arpith")
                        post_reply_to_source(
                            "bro switched to arpith mode vro",
                            source_message=msg,
                        )
                        print("\nWaiting for requests...\n")
                    elif is_switch_to_lucy(msg):
                        print("\n'Lucy' trigger detected! Switching mode back to Lucy Mary Raj...")
                        set_persona_mode("lucy")
                        post_reply_to_source(
                            "THAT RASCAL OVER THERE! Lucy Mary Raj is back in charge. Better be careful!",
                            source_message=msg,
                        )
                        print("\nWaiting for requests...\n")
                    else:
                        current_mode = get_current_persona_mode()
                        if current_mode == "eshant":
                            print("\nGeneral mention detected (Current mode: Eshant)! Invoking Eshant AI...")
                            handle_eshant_request(msg)
                        elif current_mode == "arpith":
                            print("\nGeneral mention detected (Current mode: Arpith)! Invoking Arpith AI...")
                            handle_arpith_request(msg)
                        else:
                            print("\nGeneral mention detected (Current mode: Lucy)! Invoking Lucy Mary Raj...")
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
