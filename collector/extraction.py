"""Extract literal published addresses only; no address generation or deobfuscation."""
import re

EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+")


def extract_text(text):
    return {m.group().rsplit('@', 1)[0] + '@' + m.group().rsplit('@', 1)[1].lower()
            for m in EMAIL.finditer(text) if len(m.group()) <= 254}

