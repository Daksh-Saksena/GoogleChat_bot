import re


SAM_ALTMAN_ACTIVATION_TEXT = "GIMME THE RAM"


def is_sam_altman_mode_command(text):
    return bool(re.search(r"\bsonny\s+ram\b", text or "", re.IGNORECASE))


def mentions_ram(text):
    return bool(re.search(r"\bram\b", text or "", re.IGNORECASE))
