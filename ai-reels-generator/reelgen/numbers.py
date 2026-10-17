"""Numbers written out in English words before an English voice reads them.

The Microsoft 'Multilingual' voices (Andrew, the default) pick the language from the text, and in an English script
about India (lakh, crore, rupees) they read the digits in Hindi: the user heard "ek lakh" for "1 lakh", and "every
number spoken in Hinglish but the script is English". Words leave them nothing to guess: "1 lakh" -> "one lakh",
"₹2.5 crore" -> "two point five crore rupees", "1,400" -> "one thousand four hundred", "2024" -> "twenty twenty-four",
"18%" -> "eighteen percent", "3rd" -> "third", "1990s" -> "nineteen nineties", "10-15" -> "ten to fifteen",
"2022-23" -> "twenty twenty-two to twenty-three", "7:30" -> "seven thirty".

Only for English narration (voice.py `_synthesize`, never a Hindi or Sarvam voice or mixed Hinglish, where the Hindi
reading is wanted). Indian grouping ("1,00,000") is read in lakh and crore; Western grouping in thousands and millions.
Digits glued to letters (5G, G20, 80C) and long digit runs (phone numbers) are left as written; COVID-19 is read
"COVID-nineteen".
"""

from __future__ import annotations

import re

try:
    from num2words import num2words
except ImportError:  # not installed yet (an app updated without its packages): numbers stay as written
    num2words = None

UNITS = r"lakh|lakhs|crore|crores|thousand|million|billion|trillion|hundred"
CURRENCY = {"₹": "rupees", "rs": "rupees", "rs.": "rupees", "inr": "rupees", "$": "dollars", "usd": "dollars",
            "€": "euros", "£": "pounds"}
NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
# Not inside a word (5G, G20, COVID-19 stay as written): no letter or digit right before or after.
_TIME = re.compile(r"(?<![\w:.])(\d{1,2}):(\d{2})(?![\w:])")
_TOKEN = re.compile(
    rf"(?<![\w.:])(?P<cur>₹|\$|€|£|(?:Rs\.?|INR|USD)\s?)?(?P<num>{NUM})"
    rf"(?:(?P<range>\s?[-–]\s?)(?P<num2>{NUM}))?"
    rf"(?P<suffix>%|st|nd|rd|th|s(?=\b))?"
    rf"(?:\s?(?P<unit>{UNITS})\b)?(?![\w:])", re.I)


def _words(n: str, indian: bool = False) -> str:
    whole, _, frac = n.replace(",", "").partition(".")
    text = num2words(int(whole), lang="en_IN" if indian else "en").replace(",", "")
    if frac:  # 2.05 -> two point zero five (every digit, as said)
        text += " point " + " ".join(num2words(int(d)) for d in frac)
    return text


def _indian(n: str) -> bool:
    """1,00,000 is written the Indian way (lakh, crore); 100,000 the Western way."""
    return bool(re.fullmatch(r"\d{1,2}(,\d{2})+,\d{3}(\.\d+)?", n))


def _year(n: str) -> bool:
    return "," not in n and "." not in n and len(n) == 4 and 1100 <= int(n) <= 2099


def _say(m: re.Match) -> str:
    raw, num, num2, suffix = m.group(0), m.group("num"), m.group("num2"), (m.group("suffix") or "")
    cur = (m.group("cur") or "").strip().lower()
    unit = (m.group("unit") or "").lower()
    digits = num.replace(",", "").split(".")[0]
    if len(digits) > 12 or (len(digits) > 9 and "," not in num and not cur):  # a phone number, an ID: as written
        return raw
    if suffix.lower() in ("st", "nd", "rd", "th") and "." not in num and not num2:
        return num2words(int(digits), to="ordinal", lang="en")
    plural = suffix.lower() == "s" and not num2
    if plural and _year(num):  # the 1990s
        spoken = num2words(int(num), to="year", lang="en")
        return (spoken[:-1] + "ies" if spoken.endswith("y") else spoken + "s") + (f" {unit}" if unit else "")
    if plural and "." not in num and "," not in num and int(digits) % 10 == 0 and 10 <= int(digits) <= 90:
        tens = num2words(int(digits))  # the 20s -> the twenties
        return tens[:-1] + "ies" if tens.endswith("y") else tens + "s"
    if suffix.lower() == "s" and not plural:
        return raw
    year = not cur and not unit and suffix != "%" and _year(num) and (not num2 or _year(num2) or len(num2) == 2)
    say = (lambda x: num2words(int(x), to="year", lang="en") if len(x) == 4 else _words(x)) if year \
        else (lambda x: _words(x, _indian(x)))
    spoken = say(num) + (f" to {say(num2)}" if num2 else "")
    if suffix == "%":
        spoken += " percent"
    if unit:
        spoken += f" {unit}"
    if cur:
        spoken += f" {CURRENCY.get(cur, '')}".rstrip()
    if plural:  # '20s' after a number that isn't a year: as written
        return raw
    return spoken


def speakable(text: str) -> str:
    """`text` with its numbers in English words (see the module's notes); everything else unchanged."""
    if num2words is None or not re.search(r"\d", text):
        return text
    text = _TIME.sub(lambda m: num2words(int(m.group(1))) + (
        "" if m.group(2) == "00" else " oh " + num2words(int(m.group(2))) if m.group(2).startswith("0")
        else " " + num2words(int(m.group(2)))), text)
    return _TOKEN.sub(_say, text)
