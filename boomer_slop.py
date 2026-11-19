"""
Facebook boomer inspirational quotes and AI slop generator for Sonny.
Generates unhinged boomer life advice, minion memes, and over-the-top blessings.
"""

import os
import random
import re

BOOMER_FALLBACK_TEMPLATES = [
    (
        "🌹✨ 'LIFE IS LIKE A CUP OF COFFEE... IT'S ALL ABOUT HOW YOU MAKE IT!!' ☕❤️ Kids today will NEVER understand winding a cassette tape with a pencil! 😂🚜 TYPE AMEN TO CLAIM THIS BLESSING!! 🙏✝️ SHARE IF YOU AGREE!! 🇺🇸🦅",
        "minion good morning",
    ),
    (
        "Good morning to everyone EXCEPT people who don't return shopping carts!! 🛒😡 Remember when we drank water straight from the garden hose and TURNED OUT FINE?! 🌸🌼 Drop a heart ❤️ if you survived childhood without an iPad! AMEN! 🙏",
        "boomer facebook minion",
    ),
    (
        "☕ 'BEFORE YOU DRINK YOUR MORNING COFFEE, REMEMBER TO COUNT YOUR BLESSINGS AND NOT YOUR PROBLEMS!!' 🌅🕊️ No GPS back in 1974, just pure common sense and road maps!! 🗺️🚗 SHARE TO SPREAD SUNSHINE!! 🌻☀️",
        "good morning flowers blessed",
    ),
    (
        "👵 DO NOT LET THE WORLD STEAL YOUR JOY TODAY!! 💖🌟 The devil saw me wake up this morning and said 'OH CRAP SHE'S UP'!! 😈😂 Type AMEN if God woke you up today!! ✝️🙏💐",
        "minion laughing funny",
    ),
    (
        "DIAGNOSED WITH: Too Blessed To Be Stressed!! 🌺🙏 Kids nowadays can't even read CURSIVE writing or dial a rotary phone!! ☎️🤦‍♂️ Put this on your wall if you still believe in HUGS and HARD WORK!! 💪🌾❤️",
        "inspirational quote sunset",
    ),
    (
        "☕ 'MAY YOUR COFFEE BE STRONG AND YOUR FAITH STRONGER!!' ✝️✨ If you love Jesus and your grandkids, give this a BIG SHARE!! 👵👶 Don't scroll without saying GOOD MORNING!! 🌅🌹",
        "coffee morning blessings",
    ),
    (
        "🦅 FREEDOM ISN'T FREE!! 🇺🇸 Just a reminder that we used to leave the front door unlocked and play outside until the streetlights came on! 🚲🏡 Who misses the GOOD OLD DAYS?! Share if you remember!! 👏❤️",
        "blessed day gif",
    ),
    (
        "🌸✨ A warm cup of tea and a prayer for anyone fighting a battle nobody knows about!! 🫖💐 You are stronger than your storm!! Drop an AMEN if you needed this reminder today!! 🙏🌈💖",
        "glitter roses good morning",
    ),
]

BOOMER_GIF_QUERIES = [
    "minion good morning",
    "boomer facebook minion",
    "good morning flowers blessed",
    "minion laughing funny",
    "inspirational quote sunset",
    "coffee morning blessings",
    "blessed day gif",
    "glitter roses good morning",
    "minion coffee meme",
    "happy sunday blessings",
]

BOOMER_PROMPT = """You generate unhinged, authentic Facebook boomer inspirational quotes and AI slop.
Think:
- Excessive random emojis (☕, 🌹, 🌸, 🙏, 😂, 🦅, 🇺🇸, ✝️, 🚜, 👵, 🌻).
- ALL CAPS on random words or whole sentences.
- Terrible font/inspirational meme vibes: fake-deep life advice, nostalgia for cassette tapes / rotary phones / garden hoses / drinking water outside, hating phones/technology/kids today, aggressive blessings, and "SHARE IF YOU AGREE!!", "AMEN!!", "TYPE AMEN TO CLAIM THIS BLESSING", "DON'T SCROLL WITHOUT SAYING GOOD MORNING!!".
- Keep it under 2-3 short punchy sentences."""


def is_boomer_slop_request(message):
    """Detects explicit user request for a Facebook boomer quote or AI slop."""
    if not message:
        return False
    text = message.get("text", "") if isinstance(message, dict) else str(message)
    text = text.lower()
    patterns = [
        r"\bboomer\s*(quote|slop|meme)?\b",
        r"\bfacebook\s*(quote|post|slop|meme)?\b",
        r"\bshitpost\b",
        r"\binspirational\s*quote\b",
        r"\bai\s*slop\b",
    ]
    return any(bool(re.search(pat, text)) for pat in patterns)


def generate_boomer_slop_post(client=None, model=None, search_gif_fn=None):
    """
    Generates a boomer inspirational quote / AI slop post.
    Returns a formatted string containing the quote and an unfurlable Tenor GIF link.
    """
    quote_text = None
    chosen_query = random.choice(BOOMER_GIF_QUERIES)

    if client:
        try:
            target_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            response = client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": BOOMER_PROMPT},
                    {
                        "role": "user",
                        "content": "Generate a Facebook boomer inspirational quote / AI slop meme text right now.",
                    },
                ],
                max_tokens=120,
                temperature=1.0,
            )
            generated = response.choices[0].message.content.strip()
            if generated:
                quote_text = generated
        except Exception as e:
            print(f"Error generating boomer quote via LLM: {e}")

    if not quote_text:
        template, fallback_query = random.choice(BOOMER_FALLBACK_TEMPLATES)
        quote_text = template
        chosen_query = fallback_query

    gif_url = None
    if search_gif_fn:
        try:
            gif_url = search_gif_fn(chosen_query)
        except Exception as e:
            print(f"Error searching GIF for boomer post: {e}")

    if not gif_url:
        gif_url = "https://tenor.com/view/morning-vec50-gif-22247715"

    return f"{quote_text}\n\n{gif_url}"
