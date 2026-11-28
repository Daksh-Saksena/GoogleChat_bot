import re


SAM_ALTMAN_ACTIVATION_TEXT = "GIMME THE RAM"
SAM_ALTMAN_DEACTIVATION_TEXT = "ram altman disabled"
DAKSH_REPLY_EMAIL = "dakshsaksena2011@gmail.com"
DAKSH_REPLY_TEXT = "meet me after 3 over there"


def is_daksh_reply_user(sender):
    if not sender:
        return False
    return (sender.get("email") or "").strip().casefold() == DAKSH_REPLY_EMAIL


def is_sam_altman_mode_command(text):
    return bool(re.search(r"\bsonny\s+ram\b", text or "", re.IGNORECASE))


def is_sam_altman_deactivation_command(text):
    return bool(re.search(r"\bsonny\s+no\s+ram\b", text or "", re.IGNORECASE))


def mentions_ram(text):
    return bool(re.search(r"\bram\b", text or "", re.IGNORECASE))
